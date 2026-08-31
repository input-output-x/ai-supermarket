<template>
  <div class="shelf">
    <section class="card">
      <div class="shelf-head">
        <h2>Agent 货架</h2>
        <div class="plan-switch">
          <span>当前客户套餐：</span>
          <button
            v-for="p in plans"
            :key="p"
            :class="['plan-btn', { active: plan === p }]"
            @click="switchPlan(p)"
          >{{ planLabel(p) }}</button>
        </div>
      </div>
      <p class="hint">
        客户登录后按套餐可见不同 Agent；锁定的 Agent 需升级套餐。下方为演示体验密钥切换。
      </p>

      <div v-for="cat in categories" :key="cat" class="cat-block">
        <h3>{{ cat }}</h3>
        <div class="cards">
          <div
            v-for="a in agentsByCat(cat)"
            :key="a.id"
            :class="['agent-card', { locked: a.locked }]"
            @click="openAgent(a)"
          >
            <div class="agent-icon">{{ a.icon }}</div>
            <div class="agent-name">{{ a.name }}</div>
            <div class="agent-desc">{{ a.description }}</div>
            <div v-if="a.locked" class="lock">🔒 需 {{ planLabel(a.required_plan) }}</div>
            <div v-else class="open">点击使用 →</div>
          </div>
        </div>
      </div>
    </section>

    <!-- 运行弹窗 -->
    <div v-if="modalAgent" class="modal-mask" @click.self="closeModal">
      <div class="modal">
        <div class="modal-head">
          <span class="agent-icon">{{ modalAgent.icon }}</span>
          <h3>{{ modalAgent.name }}</h3>
          <button class="close" @click="closeModal">✕</button>
        </div>
        <p class="modal-desc">{{ modalAgent.description }}</p>

        <div class="modal-form">
          <label v-for="sch in modalAgent.input_schema" :key="sch.key">
            <span>{{ sch.label }}<i v-if="sch.required"> *</i></span>
            <input v-if="sch.type === 'text'" v-model="formValues[sch.key]" :placeholder="sch.label" />
            <textarea v-else-if="sch.type === 'textarea'" v-model="formValues[sch.key]" rows="4" :placeholder="sch.label"></textarea>
            <select v-else-if="sch.type === 'select'" v-model="formValues[sch.key]">
              <option v-for="o in (sch.options || [])" :key="o" :value="o">{{ o }}</option>
            </select>
            <input v-else-if="sch.type === 'file'" type="file" accept="image/*" @change="onModalFile($event, sch.key)" />
          </label>
        </div>

        <button class="run-btn" :disabled="submitting" @click="submitRun">
          {{ submitting ? '运行中...' : '运行 Agent' }}
        </button>

        <div v-if="errorMsg" class="error">{{ errorMsg }}</div>

        <div v-if="resultText" class="result">
          <h4>运行结果</h4>
          <div v-if="resultKind === 'video'" class="video-result">
            <p>{{ resultText }}</p>
            <RouterLink class="link-btn" to="/">去口播视频工坊查看 →</RouterLink>
          </div>
          <pre v-else class="result-text">{{ resultText }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getAgents, runAgent, getDemoKey } from '../api.js'

const plans = ['free', 'pro', 'enterprise']
const plan = ref('free')
const agents = ref([])
const loading = ref(false)

const modalAgent = ref(null)
const formValues = ref({})
const fileMap = ref({})
const submitting = ref(false)
const resultText = ref('')
const resultKind = ref('')
const errorMsg = ref('')

const categories = ['内容生产', '专业服务']

function planLabel(p) {
  return { free: '免费版', pro: '专业版', enterprise: '企业版' }[p] || p
}

function agentsByCat(cat) {
  return agents.value.filter((a) => a.category === cat)
}

async function loadShelf() {
  loading.value = true
  try {
    const { data } = await getAgents(getDemoKey(plan.value))
    agents.value = data.agents || []
  } catch (e) {
    errorMsg.value = '加载货架失败：' + (e.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

function switchPlan(p) {
  plan.value = p
  localStorage.setItem('shelf_plan', p)
  loadShelf()
}

function openAgent(a) {
  if (a.locked) {
    alert(`该 Agent 需「${planLabel(a.required_plan)}」套餐，当前为「${planLabel(plan.value)}」`)
    return
  }
  modalAgent.value = a
  formValues.value = {}
  fileMap.value = {}
  resultText.value = ''
  resultKind.value = ''
  errorMsg.value = ''
}

function closeModal() {
  modalAgent.value = null
}

function onModalFile(e, key) {
  const f = e.target.files[0]
  if (f) fileMap.value[key] = f
}

async function submitRun() {
  if (!modalAgent.value) return
  submitting.value = true
  errorMsg.value = ''
  resultText.value = ''
  try {
    const isVideo = modalAgent.value.handler === 'video'
    let payload
    if (isVideo) {
      payload = new FormData()
      for (const sch of modalAgent.value.input_schema) {
        if (sch.type === 'file') {
          if (fileMap.value[sch.key]) payload.append(sch.key, fileMap.value[sch.key])
        } else {
          payload.append(sch.key, formValues.value[sch.key] || '')
        }
      }
    } else {
      payload = {}
      for (const sch of modalAgent.value.input_schema) {
        payload[sch.key] = formValues.value[sch.key] || ''
      }
    }
    const { data } = await runAgent(modalAgent.value.id, payload, isVideo, getDemoKey(plan.value))
    resultKind.value = data.kind
    if (data.kind === 'video') {
      resultText.value = data.message || `已创建任务 #${data.job_id}`
    } else {
      resultText.value = data.result || JSON.stringify(data)
    }
  } catch (e) {
    errorMsg.value = '运行失败：' + (e.response?.data?.detail || e.message)
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  const saved = localStorage.getItem('shelf_plan')
  if (saved) plan.value = saved
  loadShelf()
})
</script>

<style scoped>
.shelf { max-width: 1000px; margin: 0 auto; }
.card {
  background: #fff;
  border-radius: 16px;
  padding: 24px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.06);
}
.shelf-head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
.shelf-head h2 { margin: 0; font-size: 20px; }
.plan-switch { display: flex; align-items: center; gap: 8px; font-size: 14px; color: #374151; }
.plan-btn {
  padding: 6px 14px;
  border: 1px solid #d1d5db;
  background: #fff;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
}
.plan-btn.active { background: #2563eb; color: #fff; border-color: #2563eb; }
.hint { color: #6b7280; font-size: 13px; margin: 8px 0 20px; }
.cat-block { margin-top: 16px; }
.cat-block h3 { font-size: 15px; color: #374151; margin: 12px 0; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 14px; }
.agent-card {
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 16px;
  cursor: pointer;
  transition: 0.15s;
  background: #fafafa;
}
.agent-card:hover { border-color: #2563eb; transform: translateY(-2px); }
.agent-card.locked { opacity: 0.6; cursor: not-allowed; }
.agent-icon { font-size: 28px; }
.agent-name { font-weight: 600; margin: 8px 0 4px; }
.agent-desc { font-size: 12px; color: #6b7280; min-height: 32px; }
.lock { margin-top: 8px; font-size: 12px; color: #b45309; }
.open { margin-top: 8px; font-size: 12px; color: #2563eb; }

.modal-mask {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.45);
  display: flex; align-items: center; justify-content: center;
  z-index: 50;
}
.modal {
  background: #fff;
  border-radius: 16px;
  padding: 24px;
  width: 90%; max-width: 520px;
  max-height: 86vh; overflow-y: auto;
}
.modal-head { display: flex; align-items: center; gap: 10px; }
.modal-head h3 { margin: 0; flex: 1; }
.close { border: none; background: none; font-size: 18px; cursor: pointer; color: #6b7280; }
.modal-desc { font-size: 13px; color: #6b7280; margin: 8px 0 16px; }
.modal-form { display: flex; flex-direction: column; gap: 14px; }
.modal-form label { display: flex; flex-direction: column; gap: 6px; font-size: 14px; color: #374151; }
.modal-form input, .modal-form textarea, .modal-form select {
  padding: 10px 12px; border: 1px solid #d1d5db; border-radius: 8px; font-size: 14px;
}
.modal-form textarea { resize: vertical; }
.run-btn {
  margin-top: 18px; width: 100%;
  padding: 12px; background: #2563eb; color: #fff; border: none; border-radius: 8px; cursor: pointer; font-size: 15px;
}
.run-btn:disabled { background: #93c5fd; cursor: not-allowed; }
.error { color: #991b1b; font-size: 13px; margin-top: 10px; }
.result { margin-top: 18px; border-top: 1px solid #e5e7eb; padding-top: 14px; }
.result h4 { margin: 0 0 8px; font-size: 14px; }
.result-text { white-space: pre-wrap; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; font-size: 13px; max-height: 300px; overflow-y: auto; }
.video-result p { font-size: 14px; color: #374151; }
.link-btn { display: inline-block; margin-top: 8px; color: #2563eb; font-size: 14px; }
</style>
