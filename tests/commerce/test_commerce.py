import asyncio
import pytest
from src.services.commerce_service import CommerceService
from src.infrastructure.persistence.commerce_repository import CommerceRepository
from src.domain.models.commerce import ProductInput


def product():
    return ProductInput(sku='SKU-1', title='演示资料', description='自有数字资料', price=12,
                        images=['https://example.org/image.png'], delivery_type='stock')


def test_preview_publish_is_distinct_and_deduplicated(tmp_path):
    repo = CommerceRepository(str(tmp_path / 'preview.sqlite3'))
    service = CommerceService(repo, mode='preview')
    item = repo.save_product(product())
    repo.add_stock(item['id'], ['preview-only'])
    a = asyncio.run(service.publish(item['id'], 'demo'))
    b = asyncio.run(service.publish(item['id'], 'demo'))
    assert a['id'] == b['id']
    assert a['status'] == 'preview'
    assert a['seller_item_id'] is None


def test_stock_order_replay_and_depletion(tmp_path):
    repo = CommerceRepository(str(tmp_path / 'preview.sqlite3'))
    service = CommerceService(repo, mode='preview')
    item = repo.save_product(product())
    repo.add_stock(item['id'], ['secret-A'])
    first = service.simulate_order(item['id'], 'order-1', 'paid')
    assert first['status'] == 'delivered'
    assert service.simulate_order(item['id'], 'order-1', 'paid')['id'] == first['id']
    assert service.simulate_order(item['id'], 'order-2', 'paid')['status'] == 'out_of_stock'
    assert 'secret-A' not in str(repo.executions())


def test_refund_and_unknown_send_do_not_consume_again(tmp_path):
    repo = CommerceRepository(str(tmp_path / 'preview.sqlite3'))
    service = CommerceService(repo, mode='preview')
    item = repo.save_product(product())
    repo.add_stock(item['id'], ['A', 'B'])
    assert service.simulate_order(item['id'], 'refund', 'cancelled')['status'] == 'ignored'
    unknown = service.simulate_order(item['id'], 'unknown', 'paid', send_result='unknown')
    assert unknown['status'] == 'unknown'
    assert service.simulate_order(item['id'], 'unknown', 'paid')['status'] == 'unknown'
    assert repo.stock_count(item['id']) == 1


def test_product_requires_real_fields():
    with pytest.raises(ValueError):
        ProductInput(sku='', title='', description='', price=0, images=[])


def test_pending_and_empty_orders_can_progress_without_double_delivery(tmp_path):
    repo = CommerceRepository(str(tmp_path / 'preview.sqlite3'))
    service = CommerceService(repo)
    item = repo.save_product(product())
    assert service.simulate_order(item['id'], 'later', 'pending_payment')['status'] == 'ignored'
    assert service.simulate_order(item['id'], 'later', 'paid')['status'] == 'out_of_stock'
    repo.add_stock(item['id'], ['A', 'B'])
    assert service.simulate_order(item['id'], 'later', 'paid')['status'] == 'delivered'
    service.simulate_order(item['id'], 'later', 'paid')
    assert repo.stock_count(item['id']) == 1
    assert service.preview_relist(item['id'], 'later', False)['eligible']
    assert not service.preview_relist(item['id'], 'later', True)['eligible']


def test_bound_live_stock_import_is_explicitly_rejected(tmp_path):
    repo = CommerceRepository(str(tmp_path / 'live.sqlite3'))
    service = CommerceService(repo, mode='live')
    item = repo.save_product(product())
    listing = repo.stage_listing(item['id'], 'acct', 'live')
    repo.update_listing(listing['id'], status='ready', card_id=3)
    with pytest.raises(ValueError, match='卖家引擎'):
        service.import_stock(item['id'], ['new'])
    assert repo.stock_count(item['id']) == 0
