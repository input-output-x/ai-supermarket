// 套餐额度文案（与后端 PLAN_QUOTA 保持一致）
const PLAN_QUOTA = {
  free: 10,
  pro: 300,
  enterprise: null, // 不限
}

export function get_quota_text(plan) {
  const q = PLAN_QUOTA[plan]
  if (q === null || q === undefined) return '不限量'
  return `每月 ${q} 次调用`
}
