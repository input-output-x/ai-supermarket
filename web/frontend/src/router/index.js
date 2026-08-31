import { createRouter, createWebHistory } from 'vue-router'
import StudioView from '../views/StudioView.vue'
import ShelfView from '../views/ShelfView.vue'
import BillingView from '../views/BillingView.vue'

const routes = [
  { path: '/', name: 'studio', component: StudioView },
  { path: '/shelf', name: 'shelf', component: ShelfView },
  { path: '/billing', name: 'billing', component: BillingView },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
