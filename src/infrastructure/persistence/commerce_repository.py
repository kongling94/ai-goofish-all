import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from src.domain.models.commerce import ProductInput


class CommerceRepository:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY, sku TEXT UNIQUE NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS listings (
                    id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, account_id TEXT NOT NULL,
                    mode TEXT NOT NULL, status TEXT NOT NULL, seller_item_id TEXT, publish_log_id INTEGER,
                    card_id INTEGER, rule_id INTEGER, material_id INTEGER, error TEXT,
                    UNIQUE(product_id, account_id, mode));
                CREATE TABLE IF NOT EXISTS stock (
                    id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, code TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'available', order_id TEXT,
                    UNIQUE(product_id, code));
                CREATE TABLE IF NOT EXISTS preview_orders (
                    id INTEGER PRIMARY KEY, order_id TEXT UNIQUE NOT NULL, product_id INTEGER NOT NULL,
                    status TEXT NOT NULL, stock_id INTEGER);
                CREATE TABLE IF NOT EXISTS executions (
                    id INTEGER PRIMARY KEY, action TEXT, object_id TEXT, status TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            ''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_product(self, product: ProductInput):
        with self.connection() as db:
            db.execute('INSERT INTO products(sku,payload) VALUES (?,?) ON CONFLICT(sku) DO UPDATE SET payload=excluded.payload',
                       (product.sku, product.model_dump_json()))
            row = db.execute('SELECT id,payload FROM products WHERE sku=?', (product.sku,)).fetchone()
        return {'id': row['id'], **json.loads(row['payload'])}

    def products(self):
        with self.connection() as db:
            rows = db.execute('SELECT * FROM products ORDER BY id DESC').fetchall()
        return [{'id': row['id'], **json.loads(row['payload']), 'stock_count': self.stock_count(row['id'])} for row in rows]

    def product(self, product_id):
        with self.connection() as db:
            row = db.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
        if not row:
            raise LookupError('商品不存在')
        return {'id': row['id'], **json.loads(row['payload'])}

    def add_stock(self, product_id, codes):
        self.product(product_id)
        with self.connection() as db:
            db.executemany('INSERT OR IGNORE INTO stock(product_id,code) VALUES (?,?)', [(product_id, code) for code in codes])
        return self.stock_count(product_id)

    def stock_count(self, product_id):
        with self.connection() as db:
            return db.execute("SELECT COUNT(*) FROM stock WHERE product_id=? AND state='available'", (product_id,)).fetchone()[0]

    def stage_listing(self, product_id, account_id, mode):
        with self.connection() as db:
            db.execute("INSERT OR IGNORE INTO listings(product_id,account_id,mode,status) VALUES (?,?,?,'publishing')", (product_id, account_id, mode))
            return dict(db.execute('SELECT * FROM listings WHERE product_id=? AND account_id=? AND mode=?', (product_id, account_id, mode)).fetchone())

    def update_listing(self, listing_id, **values):
        columns = ','.join(f'{key}=?' for key in values)
        with self.connection() as db:
            db.execute(f'UPDATE listings SET {columns} WHERE id=?', (*values.values(), listing_id))
            return dict(db.execute('SELECT * FROM listings WHERE id=?', (listing_id,)).fetchone())

    def listings(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute('SELECT * FROM listings ORDER BY id DESC')]

    def listing(self, listing_id):
        with self.connection() as db:
            row = db.execute('SELECT * FROM listings WHERE id=?', (listing_id,)).fetchone()
        if not row:
            raise LookupError('发布记录不存在')
        return dict(row)

    def record(self, action, object_id, status):
        with self.connection() as db:
            db.execute('INSERT INTO executions(action,object_id,status) VALUES (?,?,?)', (action, str(object_id), status))

    def executions(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute('SELECT * FROM executions ORDER BY id DESC LIMIT 100')]

    def orders(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute('SELECT * FROM preview_orders ORDER BY id DESC')]

    def preview_order(self, product_id, order_id, payment_status, send_result):
        product = self.product(product_id)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT * FROM preview_orders WHERE order_id=?', (order_id,)).fetchone()
            if existing:
                if existing['product_id'] != product_id:
                    raise ValueError('订单已关联其他商品')
                if existing['status'] in ('delivered', 'unknown'):
                    return dict(existing)
            status = 'ignored'
            stock_id = None
            if payment_status == 'paid':
                if product['delivery_type'] == 'fixed':
                    if not product['fixed_content']:
                        raise ValueError('未配置固定交付内容')
                    status = 'delivered' if send_result == 'success' else 'unknown'
                else:
                    stock = db.execute("SELECT id FROM stock WHERE product_id=? AND state='available' ORDER BY id LIMIT 1", (product_id,)).fetchone()
                    if not stock:
                        status = 'out_of_stock'
                    else:
                        stock_id = stock['id']
                        status = 'delivered' if send_result == 'success' else 'unknown'
                        db.execute('UPDATE stock SET state=?,order_id=? WHERE id=?', (status, order_id, stock_id))
            db.execute('INSERT INTO preview_orders(order_id,product_id,status,stock_id) VALUES (?,?,?,?) ON CONFLICT(order_id) DO UPDATE SET status=excluded.status,stock_id=excluded.stock_id', (order_id, product_id, status, stock_id))
            return dict(db.execute('SELECT * FROM preview_orders WHERE order_id=?', (order_id,)).fetchone())

    def save_preference(self, key, value):
        with self.connection() as db:
            db.execute('INSERT INTO preferences VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(value)))

    def preferences(self):
        with self.connection() as db:
            return {row['key']: json.loads(row['value']) for row in db.execute('SELECT * FROM preferences')}
