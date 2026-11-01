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
