<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

interface Product { id: number; sku: string; title: string; price: number; stock_count: number; delivery_type: string }
interface Listing { id: number; product_id: number; account_id: string; status: string; mode: string; seller_item_id: string | null; material_id: number | null; card_id: number | null; error: string | null }
interface GuardStatus { consecutive_failures?: number; paused_by_guard?: boolean; threshold?: number; last_failure_ago_seconds?: number | null }

const route = useRoute()
const tab = ref('商品目录')
const tabs = ['商品目录', '发布记录', '客服回复', '数字库存', '订单演练', '自动续售', '卖家账号', '执行记录']
const mode = ref('preview')
const paused = ref(false)
const busy = ref(false)
const message = ref('')
const products = ref<Product[]>([])
const listings = ref<Listing[]>([])
const output = ref('')
const account = ref('demo')
const cookies = ref('')
const itemId = ref('')
const replyContent = ref('您好，商品内容和交付方式以详情为准，有问题可以留言。')
const stockProduct = ref(0)
const stockCodes = ref('')
const orderId = ref('demo-order-1')
const paymentStatus = ref('paid')
const sendResult = ref('success')
const originalListed = ref(true)
const selectedListing = ref(0)
const delay = ref(60)
const minimumStock = ref(1)
const cardId = ref(0)
const ruleId = ref(0)
const guard = ref<GuardStatus>({})
const ai = reactive({ ai_enabled: false, base_url: 'https://api.deepseek.com', model_name: 'deepseek-flash', api_key: '', max_discount_percent: 0, max_discount_amount: 0, max_bargain_rounds: 0 })
const product = reactive({ sku: '', title: '', description: '', price: 1, images: '', category: '', source_item_id: '', delivery_type: 'stock', fixed_content: '' })

async function api(path: string, method = 'GET', body?: unknown) {
  const response = await fetch('/api/commerce' + path, { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) })
  const value = await response.json()
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : JSON.stringify(value.detail))
  return value
}
async function refresh() {
  const [status, items, records] = await Promise.all([api('/status'), api('/products'), api('/listings')])
  mode.value = status.mode; paused.value = status.paused; products.value = items; listings.value = records
  guard.value = status.guard || {}
  if (!stockProduct.value && items.length) stockProduct.value = items[0].id
}
async function run(action: () => Promise<unknown>) {
  busy.value = true; message.value = ''; output.value = ''
  try { const result = await action(); output.value = JSON.stringify(result, null, 2); message.value = '操作已记录'; await refresh() }
  catch (error) { message.value = error instanceof Error ? error.message : '操作失败' }
  finally { busy.value = false }
}
async function saveProduct() {
  return api('/products', 'POST', { ...product, images: product.images.split('\n').map(v => v.trim()).filter(Boolean), source_item_id: product.source_item_id || null })
}
async function createRelist() {
  const listing = listings.value.find(row => row.id === selectedListing.value)
  if (!listing?.seller_item_id || !listing.material_id || !listing.card_id) throw new Error('请选择正式发布且已绑定素材和发货卡券的记录')
  return api('/relist', 'POST', { cookie_id: listing.account_id, item_id: listing.seller_item_id, material_id: listing.material_id, card_id: listing.card_id, enabled: true, delay_seconds: delay.value, min_stock: minimumStock.value })
}
onMounted(async () => {
  if (typeof route.query.title === 'string') product.title = route.query.title
  if (typeof route.query.source === 'string') product.source_item_id = route.query.source
  try { await refresh() } catch (error) { message.value = String(error) }
})
</script>

<template>
  <main class="commerce space-y-6">
    <header class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="text-3xl font-bold">数字商品工作台</h1>
        <p class="mt-2 text-slate-500">管理自有商品、发布、客服和数字交付。</p>
      </div>
      <div class="flex flex-col items-end gap-2">
        <div class="flex items-center gap-3">
          <span class="rounded-full bg-blue-50 px-4 py-2 text-blue-700">{{ mode === 'preview' ? '演练 · 未连接闲鱼' : '正式模式 · 真实平台动作' }}</span>
          <button :disabled="busy" @click="run(() => api('/pause', 'POST', { paused: !paused }))">{{ paused ? '恢复新动作' : '暂停新动作' }}</button>
        </div>
        <div v-if="mode === 'live'" class="text-xs text-slate-500">
          熔断计数：{{ guard.consecutive_failures || 0 }} / {{ guard.threshold || 5 }}
          <span v-if="guard.paused_by_guard" class="ml-2 text-amber-600 font-medium">（已自动暂停）</span>
        </div>
      </div>
    </header>
    <div v-if="mode === 'preview'" class="rounded-xl border border-blue-100 bg-blue-50 p-4 text-sm text-blue-900">当前使用隔离演练数据，不发布真实商品、不建立账号监听、不发送消息。正式模式需在部署配置中切换并重启两个服务。</div>
    <div v-if="paused" class="rounded-xl bg-amber-50 p-4">手动派发和自动续售已暂停。已提交动作、实时消息和订单处理可能继续，请核对记录。</div>
    <nav class="flex flex-wrap gap-2"><button v-for="name in tabs" :key="name" :class="{ active: tab === name }" @click="tab = name; output = ''">{{ name }}</button></nav>
    <p v-if="message" role="status" class="rounded-xl bg-slate-100 p-3">{{ message }}</p>

    <section v-if="tab === '商品目录'" class="grid gap-6 xl:grid-cols-2">
      <form class="panel grid gap-3" @submit.prevent="run(saveProduct)">
        <h2>新增或更新自有商品</h2><p class="hint">监控结果只作选品参考，请填写自己的库存、图片和交付内容。</p>
        <label>商品编号 SKU<input v-model="product.sku" required placeholder="如 DIGITAL-001"></label>
        <label>商品标题<input v-model="product.title" required></label>
        <label>商品描述<textarea v-model="product.description" required rows="3" /></label>
        <div class="grid grid-cols-2 gap-3"><label>售价（元）<input v-model.number="product.price" required type="number" min="0.01" step="0.01"></label><label>类目提示<input v-model="product.category"></label></div>
        <label>图片地址（每行一张）<textarea v-model="product.images" required rows="2" placeholder="https://..."></textarea></label>
        <label>来源商品 ID（可选）<input v-model="product.source_item_id"></label>
        <label>交付方式<select v-model="product.delivery_type"><option value="stock">库存卡密</option><option value="fixed">固定文本</option></select></label>
        <label v-if="product.delivery_type === 'fixed'">固定交付内容<textarea v-model="product.fixed_content" required rows="3" /></label>
        <button class="primary" :disabled="busy">保存商品</button>
      </form>
      <div class="panel space-y-4"><h2>商品目录</h2><p v-if="!products.length" class="hint">先创建一个自有数字商品，再导入演练库存。</p>
        <article v-for="row in products" :key="row.id" class="rounded-xl border p-4"><div class="flex justify-between"><strong>{{ row.title }}</strong><span>¥{{ row.price }}</span></div><p class="hint">{{ row.sku }} · 本地可用库存 {{ row.stock_count }} · {{ row.delivery_type }}</p><div class="mt-3 flex gap-2"><button :disabled="busy" @click="stockProduct = row.id; tab = '数字库存'">管理库存</button><button :disabled="busy || paused" @click="run(() => api(`/products/${row.id}/publish`, 'POST', { account_id: account }))">{{ mode === 'preview' ? '演练发布' : '发布到闲鱼' }}</button></div></article>
      </div>
    </section>

    <section v-else-if="tab === '发布记录'" class="panel space-y-4"><h2>发布记录与关联</h2><label>发布账号<input v-model="account"></label><p class="hint">演练记录没有平台商品 ID。正式发布后还需绑定交付；结果未知时先核对，不重复发布。</p>
      <article v-for="row in listings" :key="row.id" class="rounded-xl border p-4 space-y-2">
        <strong>#{{ row.id }} · 商品 {{ row.product_id }} · {{ row.status }}</strong>
        <p class="hint">账号 {{ row.account_id }} · {{ row.mode }} · 平台 ID {{ row.seller_item_id || '—' }}</p>
        <p v-if="row.error" class="text-amber-700">{{ row.error }}</p>
        <div class="flex flex-wrap gap-2 mt-2">
          <button v-if="row.status === 'published_unbound'" :disabled="busy" @click="run(() => api(`/listings/${row.id}/bind`, 'POST'))">绑定库存与自动发货</button>
          <button v-if="['unknown', 'publishing'].includes(row.status)" :disabled="busy" @click="run(() => api(`/listings/${row.id}/reconcile-active`, 'POST'))">主动对账</button>
        </div>
      </article>
      <form class="grid gap-3 border-t pt-4" @submit.prevent="run(() => api(`/listings/${selectedListing}/reconcile`, 'POST', { seller_item_id: itemId }))"><h3>发布结果待核对</h3><label>记录编号<input v-model.number="selectedListing" type="number" min="1" required></label><label>人工核对的平台商品 ID<input v-model="itemId" required></label><button :disabled="busy">保存核对结果</button></form>
      <form v-if="mode === 'live'" class="grid gap-3 border-t pt-4" @submit.prevent="run(() => api(`/listings/${selectedListing}/reconcile-binding`, 'POST', { card_id: cardId, rule_id: ruleId }))"><h3>核对已有发货绑定</h3><p class="hint">绑定中断后，先在卖家引擎确认已有卡券和规则。此操作只读取核对，不重新创建。</p><label>发布记录编号<input v-model.number="selectedListing" type="number" min="1" required></label><label>已有卡券编号<input v-model.number="cardId" type="number" min="1" required></label><label>已有发货规则编号<input v-model.number="ruleId" type="number" min="1" required></label><button :disabled="busy">读取并核对绑定</button></form>
    </section>

    <section v-else-if="tab === '客服回复'" class="grid gap-6 xl:grid-cols-2"><form class="panel space-y-4" @submit.prevent="run(() => api('/replies', 'POST', { account_id: account, item_id: itemId, content: replyContent }))"><h2>商品回复</h2><label>卖家账号<input v-model="account" required></label><label>平台商品 ID<input v-model="itemId" required></label><label>回复内容<textarea v-model="replyContent" required rows="5" /></label><button class="primary" :disabled="busy">保存回复</button></form>
      <form class="panel space-y-4" @submit.prevent="run(() => api('/ai-reply', 'PUT', { account_id: account, settings: ai }))"><h2>AI 回复</h2><label class="flex gap-2"><input v-model="ai.ai_enabled" type="checkbox">启用 AI 回复</label><label>接口地址<input v-model="ai.base_url" required></label><label>模型<input v-model="ai.model_name" required></label><label>API Key<input v-model="ai.api_key" type="password" autocomplete="off"></label><p class="hint">默认不允许议价。这里的 Key 与监控分析配置分开保存。</p><button :disabled="busy">保存 AI 回复设置</button></form>
    </section>

    <section v-else-if="tab === '数字库存'" class="panel space-y-4"><h2>导入库存卡密</h2><p class="hint">演练和正式库存分别保存。正式绑定后库存交由卖家引擎维护；首版统一入口禁止再次导入补货，请在卖家引擎卡券管理中维护。本地剩余数不代表引擎实时库存。</p><label>商品<select v-model.number="stockProduct"><option v-for="row in products" :key="row.id" :value="row.id">{{ row.sku }} · {{ row.title }}</option></select></label><label>每行一个卡密<textarea v-model="stockCodes" rows="6" autocomplete="off" /></label><button :disabled="busy || !stockProduct" @click="run(async () => { const result = await api(`/products/${stockProduct}/stock`, 'POST', { codes: stockCodes.split('\n').filter(v => v.trim()) }); stockCodes = ''; return result })">导入库存</button></section>

    <section v-else-if="tab === '订单演练'" class="panel space-y-4"><h2>{{ mode === 'preview' ? '离线订单验证' : '订单列表' }}</h2><button :disabled="busy" @click="run(() => api('/orders'))">读取订单</button><form v-if="mode === 'preview'" class="space-y-3" @submit.prevent="run(() => api('/preview/orders', 'POST', { product_id: stockProduct, order_id: orderId, payment_status: paymentStatus, send_result: sendResult }))"><label>商品<select v-model.number="stockProduct"><option v-for="row in products" :key="row.id" :value="row.id">{{ row.sku }}</option></select></label><label>演练订单号<input v-model="orderId" required></label><label>订单状态<select v-model="paymentStatus"><option value="paid">已付款</option><option value="cancelled">已取消</option><option value="refunding">退款中</option><option value="pending_payment">待付款</option></select></label><label>交付边界结果<select v-model="sendResult"><option value="success">演练发送成功</option><option value="unknown">发送中断，结果未知</option></select></label><button class="primary" :disabled="busy || !stockProduct">运行离线验证</button></form></section>

    <section v-else-if="tab === '自动续售'" class="panel space-y-4"><h2>有条件续售</h2><p class="hint">仅在相关订单已交付、原商品不在售且仍有库存时允许续售，不等于任意商品上下架。</p><form v-if="mode === 'preview'" class="space-y-3" @submit.prevent="run(() => api('/preview/relist', 'POST', { product_id: stockProduct, order_id: orderId, original_listed: originalListed }))"><label>商品<select v-model.number="stockProduct"><option v-for="row in products" :key="row.id" :value="row.id">{{ row.sku }}</option></select></label><label>演练订单号<input v-model="orderId" required></label><label class="flex gap-2"><input v-model="originalListed" type="checkbox">原商品仍在售</label><button :disabled="busy">核对续售条件</button></form><form v-else class="space-y-3" @submit.prevent="run(createRelist)"><label>正式发布记录<select v-model.number="selectedListing"><option v-for="row in listings.filter(v => v.status === 'ready')" :key="row.id" :value="row.id">#{{ row.id }} · {{ row.seller_item_id }}</option></select></label><label>交付后等待秒数<input v-model.number="delay" type="number" min="0"></label><label>最低库存<input v-model.number="minimumStock" type="number" min="1"></label><button :disabled="busy">启用续售规则</button></form><button :disabled="busy" @click="run(() => api('/relist'))">读取续售规则</button></section>

    <section v-else-if="tab === '卖家账号'" class="panel space-y-4"><h2>卖家账号</h2><p class="hint">监控账号与卖家账号分别管理。演练模式不接受真实 Cookie。</p><button :disabled="busy" @click="run(() => api('/accounts'))">读取账号</button><form v-if="mode === 'live'" class="space-y-3" @submit.prevent="run(async () => { const result = await api('/accounts', 'POST', { account_id: account, cookies }); cookies = ''; return result })"><label>账号标识<input v-model="account" required></label><label>本人登录态 Cookie<textarea v-model="cookies" required rows="4" autocomplete="off" /></label><button :disabled="busy">导入并启用卖家账号</button></form></section>
    <section v-else class="panel space-y-4"><h2>执行记录</h2><p class="hint">记录动作和结果，不展示卡密或登录态。</p><button :disabled="busy" @click="run(() => api('/executions'))">读取执行记录</button></section>
    <pre v-if="output" class="panel overflow-auto whitespace-pre-wrap text-sm" aria-label="操作结果">{{ output }}</pre>
  </main>
</template>

<style scoped>
.panel { padding: 1.5rem; border: 1px solid #e2e8f0; border-radius: 1rem; background: white; }
h2 { font-size: 1.15rem; font-weight: 700; }
label { display: block; font-size: .875rem; color: #475569; }
input:not([type=checkbox]), textarea, select { display: block; width: 100%; margin-top: .35rem; padding: .65rem .8rem; border: 1px solid #cbd5e1; border-radius: .6rem; background: white; color: #0f172a; }
button { border: 1px solid #cbd5e1; border-radius: .6rem; padding: .55rem .9rem; background: white; font-size: .875rem; }
button.active, button.primary { background: #2563eb; border-color: #2563eb; color: white; }
button:disabled { opacity: .45; cursor: not-allowed; }
.hint { font-size: .8rem; line-height: 1.6; color: #64748b; }
</style>
