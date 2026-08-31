import { createRouter, createWebHistory } from 'vue-router'
import StudioView from '../views/StudioView.vue'

const routes = [
  { path: '/', name: 'studio', component: StudioView },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
