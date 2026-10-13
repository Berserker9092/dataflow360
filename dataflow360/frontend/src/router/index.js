import { createRouter, createWebHistory } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import { useAuth } from '../stores/auth'

// `meta.period` : la page dépend de la période choisie (le sélecteur s'affiche dans la barre du haut).
const routes = [
  { path: '/login', name: 'login', component: () => import('../views/Login.vue'), meta: { public: true, title: 'Connexion' } },
  {
    path: '/',
    component: AppShell,
    children: [
      { path: '', name: 'overview', component: () => import('../views/Overview.vue'), meta: { title: "Vue d'ensemble", period: true } },
      { path: 'orders', name: 'orders', component: () => import('../views/Orders.vue'), meta: { title: 'Commandes', period: true } },
      { path: 'products', name: 'products', component: () => import('../views/Products.vue'), meta: { title: 'Produits', period: true } },
      { path: 'customers', name: 'customers', component: () => import('../views/Customers.vue'), meta: { title: 'Clients', period: true } },
      { path: 'customers/:id', name: 'customer', component: () => import('../views/CustomerDetail.vue'), props: true, meta: { title: 'Fiche client' } },
      { path: 'stock', name: 'stock', component: () => import('../views/Stock.vue'), meta: { title: 'Stocks' } },
      { path: 'fraud', name: 'fraud', component: () => import('../views/Fraud.vue'), meta: { title: 'Centre fraude' } },
      { path: 'forecast', name: 'forecast', component: () => import('../views/Forecast.vue'), meta: { title: 'Prévisions' } },
      { path: 'assistant', name: 'assistant', component: () => import('../views/Assistant.vue'), meta: { title: 'Assistant IA' } },
      { path: 'live', name: 'live', component: () => import('../views/Live.vue'), meta: { title: 'Temps réel' } },
    ],
  },
  { path: '/:pathMatch(.*)*', name: 'notfound', component: () => import('../views/NotFound.vue'), meta: { public: true, title: 'Page introuvable' } },
]

const router = createRouter({ history: createWebHistory(import.meta.env.BASE_URL), routes })

router.beforeEach((to) => {
  const auth = useAuth()
  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: 'login', query: to.fullPath === '/' ? {} : { redirect: to.fullPath } }
  }
  if (to.name === 'login' && auth.isAuthenticated) return { name: 'overview' }
})
router.afterEach((to) => {
  document.title = `${to.meta.title || 'DataFlow360'} · DataFlow360`
})

export default router
