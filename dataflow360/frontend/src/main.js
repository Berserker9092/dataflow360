import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useAuth } from './stores/auth'
import { useUi } from './stores/ui'
import { usePeriod } from './stores/period'
import { setUnauthorizedHandler } from './lib/api'
import './assets/styles.css'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)

const auth = useAuth()
const ui = useUi()
const period = usePeriod()

auth.restore()
ui.applyTheme()
period.init()   // ← LE FIX : initialise les bornes de date

setUnauthorizedHandler(() => {
  auth.logout()
  router.push({ name: 'login', query: { redirect: router.currentRoute.value.fullPath } })
})

app.use(router)
app.mount('#app')
