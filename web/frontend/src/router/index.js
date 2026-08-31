import { createRouter, createWebHistory } from 'vue-router'
import StudioView from '../views/StudioView.vue'
import ShelfView from '../views/ShelfView.vue'

const routes = [
  { path: '/', name: 'studio', component: StudioView },
  { path: '/shelf', name: 'shelf', component: ShelfView },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
