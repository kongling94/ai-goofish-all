import asyncio
from urllib.parse import quote
import httpx
from src.infrastructure.external.seller_client import SellerClient, SellerError


class CommerceService:
    def __init__(self, repository, mode='preview', seller=None, monitor_running=None):
        if mode not in ('preview', 'live'):
            raise ValueError('ALL_EXECUTION_MODE 必须为 preview 或 live')
        self.repo = repository
        self.mode = mode
        self.seller = seller or SellerClient()
        self.monitor_running = monitor_running or (lambda: False)
        self.publish_lock = asyncio.Lock()

    def ensure_dispatch(self):
        if self.repo.preferences().get('paused'):
            raise ValueError('已暂停，请处理异常后解除暂停')

    async def publish(self, product_id, account_id):
        async with self.publish_lock:
            self.ensure_dispatch()
            if self.mode == 'live' and self.monitor_running():
                raise ValueError('监控采集运行中，暂不派发发布动作')
            product = self.repo.product(product_id)
            existing = next((row for row in self.repo.listings() if row['product_id'] == product_id and row['account_id'] == account_id and row['mode'] == self.mode), None)
            if existing:
                return existing
            if product['delivery_type'] == 'stock' and self.repo.stock_count(product_id) == 0:
                raise ValueError('请先导入库存卡密')
            if product['delivery_type'] == 'fixed' and not product['fixed_content']:
                raise ValueError('请先填写固定交付内容')
            listing = self.repo.stage_listing(product_id, account_id, self.mode)
            if self.mode == 'preview':
                return self.repo.update_listing(listing['id'], status='preview')
            payload = {key: product[key] for key in ('title', 'description', 'price', 'category')}
            payload.update(account_id=account_id, images=[{'url': image} for image in product['images']], delivery_method='包邮')
            try:
                material = await self.seller.request('POST', '/product-materials', {key: value for key, value in payload.items() if key != 'account_id'})
                material_id = material['material']['id']
                self.repo.update_listing(listing['id'], material_id=material_id)
                result = await self.seller.request('POST', '/product-publish', payload)
                item_id = result.get('published_item_id')
                if not item_id:
                    return self.repo.update_listing(listing['id'], status='unknown', error='平台未返回可核对的商品 ID')
                return self.repo.update_listing(listing['id'], status='published_unbound', seller_item_id=str(item_id), publish_log_id=result.get('log_id'))
            except (httpx.RequestError, SellerError, KeyError) as exc:
                if isinstance(exc, SellerError) and exc.status in (403, 429):
                    await self.pause(True)
                return self.repo.update_listing(listing['id'], status='unknown', error='发布结果待核对，不自动重试')
            finally:
                self.repo.record('publish', listing['id'], 'submitted')

    async def bind_delivery(self, listing_id):
        self.ensure_dispatch()
        listing = self.repo.listing(listing_id)
        if self.mode != 'live' or listing['mode'] != 'live' or not listing['seller_item_id']:
            raise ValueError('仅正式发布且已有平台商品 ID 的记录可绑定真实发货')
        if listing['status'] == 'ready':
            return listing
        if listing['status'] not in ('published_unbound', 'binding_failed'):
            raise ValueError('当前状态需要先核对发货规则，不能重复绑定')
        product = self.repo.product(listing['product_id'])
        self.repo.update_listing(listing_id, status='binding')
        try:
            card_id = listing['card_id']
            if not card_id:
                with self.repo.connection() as db:
                    codes = [row['code'] for row in db.execute("SELECT code FROM stock WHERE product_id=? AND state='available'", (product['id'],))]
                card = await self.seller.request('POST', '/cards', {
                    'name': product['sku'], 'type': 'data' if product['delivery_type'] == 'stock' else 'text',
                    'data_content': '\n'.join(codes), 'text_content': product['fixed_content'], 'enabled': True,
                })
                card_id = card['id']
                self.repo.update_listing(listing_id, card_id=card_id)
                with self.repo.connection() as db:
                    db.execute("UPDATE stock SET state='exported' WHERE product_id=? AND state='available'", (product['id'],))
            rule = await self.seller.request('POST', '/delivery-rules', {'keyword': listing['seller_item_id'], 'card_id': card_id, 'delivery_count': 1, 'enabled': True})
            return self.repo.update_listing(listing_id, status='ready', rule_id=rule['id'], error=None)
        except (httpx.RequestError, SellerError, KeyError):
            return self.repo.update_listing(listing_id, status='binding_unknown', error='商品已发布，发货绑定结果待核对；请勿重新发布')

    def import_stock(self, product_id, codes):
        if self.mode == 'live' and any(row['product_id'] == product_id and row['status'] not in ('published_unbound', 'unknown', 'publishing') for row in self.repo.listings()):
            raise ValueError('此商品已交由卖家引擎管理，首版不支持从统一入口补货；请在卖家引擎卡券中维护库存')
        return self.repo.add_stock(product_id, codes)

    async def pause(self, paused):
        if self.mode == 'live':
            await self.seller.request('POST', '/all/dispatch-pause', {'paused': paused})
        self.repo.save_preference('paused', paused)
        return {'paused': paused}

    async def reconcile_binding(self, listing_id, card_id, rule_id):
        listing = self.repo.listing(listing_id)
        if self.mode != 'live' or listing['status'] not in ('binding', 'binding_unknown'):
            raise ValueError('此记录不处于发货绑定待核对状态')
        card = await self.seller.request('GET', f'/cards/{card_id}')
        rule = await self.seller.request('GET', f'/delivery-rules/{rule_id}')
        product = self.repo.product(listing['product_id'])
        if card['name'] != product['sku'] or rule['card_id'] != card_id or rule['keyword'] != listing['seller_item_id'] or not card['enabled'] or not rule['enabled']:
            raise ValueError('卡券或发货规则与当前商品不匹配或未启用')
        with self.repo.connection() as db:
            db.execute("UPDATE stock SET state='exported' WHERE product_id=? AND state='available'", (product['id'],))
        return self.repo.update_listing(listing_id, card_id=card_id, rule_id=rule_id, status='ready', error=None)

    def simulate_order(self, product_id, order_id, payment_status, send_result='success'):
        self.ensure_dispatch()
        if self.mode != 'preview':
            raise ValueError('正式模式不接受模拟订单')
        result = self.repo.preview_order(product_id, order_id, payment_status, send_result)
        self.repo.record('preview_order', result['id'], result['status'])
        return result

    async def resource(self, method, path, payload=None):
        if method != 'GET':
            self.ensure_dispatch()
        if self.mode == 'preview':
            key = f'{method}:{path}'
            if method == 'GET':
                return {'mode': 'preview', 'data': self.repo.preferences().get(path, []), 'platform_connected': False}
            self.repo.save_preference(path, payload)
            self.repo.record('preview_settings', path, 'saved')
            return {'mode': 'preview', 'saved': True}
        try:
            return await self.seller.request(method, path, payload)
        except SellerError as exc:
            if exc.status in (403, 429):
                await self.pause(True)
            raise

    def preview_relist(self, product_id, order_id, original_listed):
        if self.mode != 'preview':
            raise ValueError('正式模式请使用卖家续售规则')
        order = next((row for row in self.repo.orders() if row['order_id'] == order_id and row['product_id'] == product_id), None)
        product = self.repo.product(product_id)
        has_stock = self.repo.stock_count(product_id) > 0 if product['delivery_type'] == 'stock' else bool(product['fixed_content'])
        eligible = bool(order and order['status'] == 'delivered' and not original_listed and has_stock)
        return {'mode': 'preview', 'eligible': eligible, 'published': False}
