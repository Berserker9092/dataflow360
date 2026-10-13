import { defineStore } from 'pinia'
import { api, setApiKey } from '../lib/api'

const KEY = 'df360.key'
const read = () => {
  try {
    return localStorage.getItem(KEY) || ''
  } catch {
    return ''
  }
}

export const useAuth = defineStore('auth', {
  state: () => ({ key: '', tenant: null }),
  getters: { isAuthenticated: (s) => !!s.key },
  actions: {
    restore() {
      this.key = read()
      setApiKey(this.key)
    },
    // Valide la clé auprès de l'API avant de la conserver.
    async login(key) {
      setApiKey(key.trim())
      try {
        // Pas de route /auth/me : on valide avec une route qui existe.
        await api.get('/api/v1/kpi/summary')
        this.tenant = { key: key.trim() }
      } catch (error) {
        setApiKey('')
        throw error
      }
      this.key = key.trim()
      try {
        localStorage.setItem(KEY, this.key)
      } catch {
        /* stockage indisponible */
      }
    },
    async loadTenant() {
      if (this.key && !this.tenant) this.tenant = { key: this.key }
    },
    logout() {
      this.key = ''
      this.tenant = null
      setApiKey('')
      try {
        localStorage.removeItem(KEY)
      } catch {
        /* rien */
      }
    },
  },
})
