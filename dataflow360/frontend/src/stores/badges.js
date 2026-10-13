import { defineStore } from 'pinia'
import { api } from '../lib/api'

// Compteurs affichés dans le menu (alertes de fraude en attente).
export const useBadges = defineStore('badges', {
  state: () => ({ fraud: 0 }),
  actions: {
    async refresh() {
      try {
        const alerts = await api.get('/api/v1/fraud/alerts')
this.fraud = alerts.length
      } catch {
        /* silencieux : le badge n'est qu'un confort */
      }
    },
  },
})
