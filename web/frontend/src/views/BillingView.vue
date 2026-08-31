<template>
  <div class="billing">
    <section class="card">
      <h2>套餐与计费</h2>
      <p class="hint">当前套餐：<b>{{ planLabel(currentPlan) }}</b>。升级后额度立即解锁，新计费周期重新开始。</p>

      <div class="plans">
        <div
          v-for="p in plans"
          :key="p.id"
          :class="['plan-card', { current: p.id === currentPlan, best: p.id === 'enterprise' }]"
        >
          <div class="plan-name">{{ p.label }}</div>
          <div class="plan-price">
            <span v-if="p.price_cents === 0">免费</span>
            <span v-else>¥{{ p.price_yuan }}<small>/月</small></span>
          </div>
          <ul class="plan-feats">
            <li v-if="p.id === 'free'">可用：口播视频、爆款选题</li>
            <li v-if="p.id === 'pro'">+ 口播脚本、抖音发布、客服、财税专家</li>
            <li v-if="p.id === 'enterprise'">+ 交付调度、数据复盘（全部 Agent）</li>
            <li>额度：{{ quotaText(p.id) }}</li>
          </ul>
          <button
            v-if="p.id !== currentPlan"
            class="buy-btn"
            :disabled="busy"
            @click="upgrade(p.id)"
          >{{ busy && target === p.id ? '跳转中...' : '升级到' + p.label }}</button>
          <div v-else class="cur-tag">当前套餐</div>
        </div>
      </div>

      <div v-if="msg" class="msg" :class="msgType">{{ msg }}</div>
      <div v-if="payUrl" class="pay-redirect">
        正在跳转到支付页… <a :href="payUrl" target="_blank" rel="noopener">如未跳转，点此打开</a>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getPlans, checkoutPlan, getDemoKey } from '../api.js'
import { get_quota_text } from '../quota.js'

const plans = ref([])
const currentPlan = ref('free')
const busy = ref(false)
const target = ref('')
const msg = ref('')
const msgType = ref('')
const payUrl = ref('')

function planLabel(p) {
  return { free: '免费版', pro: '专业版', enterprise: '企业版' }[p] || p
}
function quotaText(p) {
  return get_quota_text(p)
}

async function load() {
  try {
    const { data } = await getPlans()
    plans.value = data.plans || []
  } catch (e) {
    msg.value = '加载套餐失败：' + (e.response?.data?.detail || e.message)
    msgType.value = 'err'
  }
}

async function upgrade(plan) {
  busy.value = true
  target.value = plan
  msg.value = ''
  payUrl.value = ''
  try {
    const { data } = await checkoutPlan(plan, 'stripe', getDemoKey(currentPlan.value))
    if (data.status === 'ok' && data.url) {
      payUrl.value = data.url
      window.location.href = data.url
    } else if (data.status === 'unconfigured') {
      msg.value = '尚未配置支付凭证（STRIPE_SECRET_KEY）。先在 .env 填写 Stripe key 并重启服务即可收款。'
      msgType.value = 'warn'
    } else {
      msg.value = data.message || '创建结账失败'
      msgType.value = 'err'
    }
  } catch (e) {
    msg.value = '升级失败：' + (e.response?.data?.detail || e.message)
    msgType.value = 'err'
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.billing { max-width: 900px; margin: 0 auto; }
.card { background: #fff; border-radius: 16px; padding: 24px; box-shadow: 0 4px 16px rgba(0,0,0,0.06); }
.card h2 { margin: 0 0 8px; font-size: 20px; }
.hint { color: #6b7280; font-size: 13px; margin: 0 0 20px; }
.plans { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
.plan-card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 18px; background: #fafafa; display: flex; flex-direction: column; }
.plan-card.current { border-color: #2563eb; box-shadow: 0 0 0 2px rgba(37,99,235,0.15); }
.plan-card.best { background: #f0f7ff; }
.plan-name { font-weight: 700; font-size: 16px; }
.plan-price { font-size: 22px; font-weight: 700; margin: 8px 0; color: #111827; }
.plan-price small { font-size: 12px; color: #6b7280; font-weight: 400; }
.plan-feats { list-style: none; padding: 0; margin: 0 0 14px; font-size: 13px; color: #374151; flex: 1; }
.plan-feats li { margin: 6px 0; }
.buy-btn { padding: 10px; background: #2563eb; color: #fff; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }
.buy-btn:disabled { background: #93c5fd; cursor: not-allowed; }
.cur-tag { text-align: center; color: #2563eb; font-size: 13px; padding: 10px; }
.msg { margin-top: 16px; padding: 12px; border-radius: 8px; font-size: 13px; }
.msg.warn { background: #fffbeb; color: #92400e; border: 1px solid #fde68a; }
.msg.err { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
.pay-redirect { margin-top: 12px; font-size: 13px; color: #374151; }
.pay-redirect a { color: #2563eb; }
</style>
