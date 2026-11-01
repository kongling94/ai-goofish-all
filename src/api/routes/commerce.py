import os
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from src.domain.models.commerce import ProductInput, PublishInput, StockInput, PreviewOrderInput, ReconcileInput
from src.infrastructure.persistence.commerce_repository import CommerceRepository
from src.infrastructure.external.seller_client import SellerError
from src.services.commerce_service import CommerceService

router = APIRouter(prefix='/api/commerce', tags=['commerce'])
_service = None


def get_commerce():
    global _service
    if _service is None:
        from src.api.dependencies import get_process_service
        mode = os.getenv('ALL_EXECUTION_MODE', 'preview')
        path = os.getenv('ALL_DATABASE_PATH', f'data/commerce-{mode}.sqlite3')
        def monitor_running():
            return any(get_process_service().is_running(key) for key in get_process_service().processes)
        _service = CommerceService(CommerceRepository(path), mode=mode, monitor_running=monitor_running)
    return _service


@router.get('/status')
def status(service=Depends(get_commerce)):
    return {'mode': service.mode, 'paused': service.repo.preferences().get('paused', False),
            'products': len(service.repo.products()), 'listings': len(service.repo.listings()),
            'platform_connected': None if service.mode == 'live' else False, 'mode_requires_restart': True}


@router.post('/pause')
async def pause(payload: dict, service=Depends(get_commerce)):
    value = payload.get('paused')
    if not isinstance(value, bool):
        raise HTTPException(422, 'paused 必须为布尔值')
    return await service.pause(value)


@router.get('/products')
def products(service=Depends(get_commerce)):
    result = service.repo.products()
    for item in result:
        item.pop('fixed_content', None)
    return result


@router.post('/products')
def save_product(payload: ProductInput, service=Depends(get_commerce)):
    result = service.repo.save_product(payload)
    result.pop('fixed_content', None)
    return result


@router.post('/products/{product_id}/stock')
def stock(product_id: int, payload: StockInput, service=Depends(get_commerce)):
    return {'available': service.import_stock(product_id, payload.codes)}


@router.post('/products/{product_id}/publish')
async def publish(product_id: int, payload: PublishInput, service=Depends(get_commerce)):
    return await service.publish(product_id, payload.account_id)


@router.get('/listings')
def listings(service=Depends(get_commerce)):
    return service.repo.listings()


@router.post('/listings/{listing_id}/bind')
async def bind(listing_id: int, service=Depends(get_commerce)):
    return await service.bind_delivery(listing_id)


@router.post('/listings/{listing_id}/reconcile')
def reconcile(listing_id: int, payload: ReconcileInput, service=Depends(get_commerce)):
    listing = service.repo.listing(listing_id)
    if listing['mode'] != 'live' or listing['status'] not in ('unknown', 'publishing'):
        raise HTTPException(409, '此记录不处于发布待核对状态')
    return service.repo.update_listing(listing_id, seller_item_id=payload.seller_item_id,
        publish_log_id=payload.publish_log_id, status='published_unbound', error=None)


class BindingReconcileInput(BaseModel):
    card_id: int = Field(gt=0)
    rule_id: int = Field(gt=0)


@router.post('/listings/{listing_id}/reconcile-binding')
async def reconcile_binding(listing_id: int, payload: BindingReconcileInput, service=Depends(get_commerce)):
    return await service.reconcile_binding(listing_id, payload.card_id, payload.rule_id)


@router.get('/executions')
def executions(service=Depends(get_commerce)):
    return service.repo.executions()


@router.get('/orders')
async def orders(service=Depends(get_commerce)):
    if service.mode == 'preview':
        return {'mode': 'preview', 'orders': service.repo.orders()}
    return await service.resource('GET', '/api/orders')


@router.post('/preview/orders')
def preview_order(payload: PreviewOrderInput, service=Depends(get_commerce)):
    return service.simulate_order(payload.product_id, payload.order_id, payload.payment_status, payload.send_result)


@router.get('/accounts')
async def accounts(service=Depends(get_commerce)):
    if service.mode == 'preview':
        return {'mode': 'preview', 'accounts': [{'id': 'demo', 'remark': '离线演练账号'}]}
    result = await service.resource('GET', '/cookies')
    # The vendor cookie endpoint returns secrets as values; expose identifiers only.
    if isinstance(result, (dict, list)):
        return {'accounts': [{'id': key} for key in result]}
    return {'accounts': []}


class SellerAccountInput(BaseModel):
    account_id: str = Field(min_length=1, pattern=r'^[A-Za-z0-9_-]+$')
    cookies: str = Field(min_length=1)


@router.post('/accounts')
async def add_account(payload: SellerAccountInput, service=Depends(get_commerce)):
    if service.mode != 'live':
        raise HTTPException(409, '演练模式不接收真实登录态')
    await service.resource('POST', '/cookies', {'id': payload.account_id, 'value': payload.cookies})
    return {'saved': True}


class ReplyInput(BaseModel):
    account_id: str = Field(min_length=1, pattern=r'^[A-Za-z0-9_-]+$')
    item_id: str = Field(min_length=1, pattern=r'^[A-Za-z0-9_-]+$')
    content: str = Field(min_length=1)


@router.post('/replies')
async def reply(payload: ReplyInput, service=Depends(get_commerce)):
    return await service.resource('PUT', f'/item-reply/{payload.account_id}/{payload.item_id}', {'reply_content': payload.content})


class AIReplyInput(BaseModel):
    account_id: str = Field(min_length=1, pattern=r'^[A-Za-z0-9_-]+$')
    settings: dict


@router.put('/ai-reply')
async def ai_reply(payload: AIReplyInput, service=Depends(get_commerce)):
    return await service.resource('PUT', f'/ai-reply-settings/{payload.account_id}', payload.settings)


class RelistInput(BaseModel):
    cookie_id: str = Field(min_length=1)
    item_id: str = Field(min_length=1)
    material_id: int = Field(gt=0)
    card_id: int = Field(gt=0)
    enabled: bool = False
    delay_seconds: int = Field(default=60, ge=0, le=86400)
    min_stock: int = Field(default=1, ge=1)


@router.get('/relist')
async def relists(service=Depends(get_commerce)):
    return await service.resource('GET', '/api/auto-relist/rules')


@router.post('/relist')
async def relist(payload: RelistInput, service=Depends(get_commerce)):
    return await service.resource('POST', '/api/auto-relist/rules', payload.model_dump())


@router.get('/seller-logs')
async def seller_logs(service=Depends(get_commerce)):
    return await service.resource('GET', '/publish-logs')


class PreviewRelistInput(BaseModel):
    product_id: int
    order_id: str
    original_listed: bool = True


@router.post('/preview/relist')
def preview_relist(payload: PreviewRelistInput, service=Depends(get_commerce)):
    return service.preview_relist(payload.product_id, payload.order_id, payload.original_listed)
