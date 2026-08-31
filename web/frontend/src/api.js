import axios from 'axios'

const api = axios.create({
  baseURL: '/',
  timeout: 120000,
})

// 当前客户密钥（演示用）：free / pro / enterprise 体验密钥
const DEMO_KEYS = {
  free: 'sk-free-demo-2026',
  pro: 'sk-pro-demo-2026',
  enterprise: 'sk-ent-demo-2026',
}

export function getDemoKey(plan) {
  return DEMO_KEYS[plan] || DEMO_KEYS.free
}

export function getHealth() {
  return api.get('/api/health')
}

// 货架：按当前客户套餐返回可用/锁定 Agent 列表
export function getAgents(apiKey) {
  return api.get('/api/agents', { headers: apiKey ? { 'X-API-Key': apiKey } : {} })
}

// 运行某个 Agent（video 走 multipart，其余走 JSON）
export function runAgent(agentId, payload, isFormData, apiKey) {
  const headers = { 'X-API-Key': apiKey || '' }
  if (isFormData) headers['Content-Type'] = 'multipart/form-data'
  return api.post(`/api/agents/${agentId}/run`, payload, { headers })
}

// 当前客户使用计量（额度/已用/按 Agent 分布）
export function getUsage(apiKey) {
  return api.get('/api/usage', { headers: apiKey ? { 'X-API-Key': apiKey } : {} })
}

export function listVideos() {
  return api.get('/api/videos')
}

export function getVideo(id) {
  return api.get(`/api/videos/${id}`)
}

export function createVideo(formData) {
  return api.post('/api/videos', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function downloadVideo(id, type = 'video') {
  return api.get(`/api/videos/${id}/download?type=${type}`, { responseType: 'blob' })
}
