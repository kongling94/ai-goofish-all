import asyncio
import httpx
from src.services.commerce_service import CommerceService
from src.infrastructure.external.seller_client import SellerClient
from src.infrastructure.persistence.commerce_repository import CommerceRepository
from src.domain.models.commerce import ProductInput


def test_live_publish_maps_images_and_never_repeats_after_unknown(tmp_path):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path == '/all/service-login':
            return httpx.Response(200, json={'success': True, 'token': 'test-token'})
        if request.url.path == '/product-materials':
            return httpx.Response(200, json={'material': {'id': 2}})
        raise httpx.ReadTimeout('response lost', request=request)
    seller = SellerClient('http://seller.test', 'admin', 'test', httpx.MockTransport(handler))
    repo = CommerceRepository(str(tmp_path / 'live.sqlite3'))
    service = CommerceService(repo, 'live', seller)
    item = repo.save_product(ProductInput(sku='A', title='A', description='A', price=1, images=['https://example.org/a'], delivery_type='fixed', fixed_content='test-only'))
    first = asyncio.run(service.publish(item['id'], 'acct'))
    assert first['status'] == 'unknown'
    assert asyncio.run(service.publish(item['id'], 'acct'))['id'] == first['id']
    assert calls.count('/product-publish') == 1


def test_published_item_survives_binding_failure(tmp_path):
    import json
    def handler(request):
        if request.url.path == '/all/service-login':
            return httpx.Response(200, json={'success': True, 'token': 'token'})
        if request.url.path == '/product-materials':
            return httpx.Response(200, json={'material': {'id': 2}})
        if request.url.path == '/product-publish':
            body = json.loads(request.content)
            assert body['images'] == [{'url': 'https://example.org/a'}]
            return httpx.Response(200, json={'success': True, 'published_item_id': 'platform-99', 'log_id': 7})
        if request.url.path == '/cards':
            return httpx.Response(200, json={'id': 4})
        return httpx.Response(500, json={'detail': 'failed'})
    seller = SellerClient('http://seller.test', 'admin', 'test', httpx.MockTransport(handler))
    repo = CommerceRepository(str(tmp_path / 'live.sqlite3'))
    service = CommerceService(repo, 'live', seller)
    item = repo.save_product(ProductInput(sku='A', title='A', description='A', price=1, images=['https://example.org/a'], delivery_type='fixed', fixed_content='x'))
    listing = asyncio.run(service.publish(item['id'], 'acct'))
    bound = asyncio.run(service.bind_delivery(listing['id']))
    assert bound['seller_item_id'] == 'platform-99'
    assert bound['status'] == 'binding_unknown'
    assert bound['card_id'] == 4


def test_preview_never_calls_seller(tmp_path):
    def handler(request):
        raise AssertionError('preview must not reach external service')
    seller = SellerClient('http://seller.test', transport=httpx.MockTransport(handler))
    service = CommerceService(CommerceRepository(str(tmp_path / 'preview.sqlite3')), seller=seller)
    assert asyncio.run(service.resource('POST', '/item-reply/demo/1', {'reply_content': 'demo'}))['mode'] == 'preview'


def test_binding_recovery_reads_existing_resources_without_recreating(tmp_path):
    import pytest
    calls = []
    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path == '/all/service-login':
            return httpx.Response(200, json={'success': True, 'token': 'token'})
        if request.url.path == '/cards/4':
            return httpx.Response(200, json={'id': 4, 'name': 'A', 'enabled': True})
        return httpx.Response(200, json={'id': 5, 'card_id': 4, 'keyword': 'platform-99', 'enabled': True})
    seller = SellerClient('http://seller.test', 'admin', 'test', httpx.MockTransport(handler))
    repo = CommerceRepository(str(tmp_path / 'live.sqlite3'))
    service = CommerceService(repo, 'live', seller)
    item = repo.save_product(ProductInput(sku='A', title='A', description='A', price=1, images=['https://example.org/a']))
    listing = repo.stage_listing(item['id'], 'acct', 'live')
    repo.update_listing(listing['id'], status='binding_unknown', seller_item_id='platform-99')
    recovered = asyncio.run(service.reconcile_binding(listing['id'], 4, 5))
    assert recovered['status'] == 'ready'
    assert ('GET', '/cards/4') in calls
    assert ('GET', '/delivery-rules/5') in calls
    assert all(method == 'GET' for method, path in calls if path != '/all/service-login')


def test_pause_is_forwarded_before_reporting_success(tmp_path):
    import json
    calls = []
    def handler(request):
        if request.url.path == '/all/service-login':
            return httpx.Response(200, json={'success': True, 'token': 'token'})
        calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={'paused': True})
    seller = SellerClient('http://seller.test', 'admin', 'test', httpx.MockTransport(handler))
    service = CommerceService(CommerceRepository(str(tmp_path / 'live.sqlite3')), 'live', seller)
    assert asyncio.run(service.pause(True)) == {'paused': True}
    assert calls == [('/all/dispatch-pause', {'paused': True})]
    assert service.repo.preferences()['paused']


def test_rate_limit_pause_also_reaches_seller_engine(tmp_path):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path == '/all/service-login':
            return httpx.Response(200, json={'success': True, 'token': 'token'})
        if request.url.path == '/all/dispatch-pause':
            return httpx.Response(200, json={'paused': True})
        return httpx.Response(429, json={'detail': 'rate limit'})
    seller = SellerClient('http://seller.test', 'admin', 'test', httpx.MockTransport(handler))
    service = CommerceService(CommerceRepository(str(tmp_path / 'live.sqlite3')), 'live', seller)
    import pytest
    from src.infrastructure.external.seller_client import SellerError
    with pytest.raises(SellerError):
        asyncio.run(service.resource('POST', '/cookies', {'id': 'acct', 'value': 'test'}))
    assert service.repo.preferences()['paused']
    assert '/all/dispatch-pause' in calls
