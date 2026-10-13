import { defineStore } from 'pinia'
import { api } from '../lib/api'
import { addDays, todayIso } from '../lib/dates'

export const PRESETS = [
  { value: '7d', label: '7 j', days: 7 },
  { value: '30d', label: '30 j', days: 30 },
  { value: '90d', label: '90 j', days: 90 },
  { value: '365d', label: '12 mois', days: 365 },
  { value: 'all', label: 'Tout', days: null },
  { value: 'custom', label: 'Personnalisé', days: null },
]
export const COMPARES = [
  { value: 'prev', label: 'Période précédente' },
  { value: 'year', label: 'Année précédente' },
  { value: 'none', label: 'Aucune comparaison' },
]

const read = (key, fallback) => {
  try {
    return localStorage.getItem(key) || fallback
  } catch {
    return fallback
  }
}
const write = (key, value) => {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* rien */
  }
}

// Les périodes sont ancrées sur la DERNIÈRE commande connue (pas sur « aujourd'hui »),
// sinon un jeu de données un peu ancien afficherait des graphiques vides.
export const usePeriod = defineStore('period', {
  state: () => ({
    preset: read('df360.preset', '30d'),
    compare: read('df360.compare', 'prev'),
    from: '',
    to: '',
    min: null,
    max: null,
    ready: false,
  }),
  getters: {
    params: (s) => ({ from: s.from, to: s.to, compare: s.compare }),
    query: (s) => `from=${s.from}&to=${s.to}&compare=${s.compare}`,
    anchor: (s) => s.max || todayIso(),
  },
  actions: {
    async init() {
      if (this.ready) return
      try {
        // Pas de route bounds : on utilise des dates par défaut
        const bounds = { min: '2020-01-01', max: new Date().toISOString().split('T')[0] }
        this.min = bounds.min
        this.max = bounds.max
      } catch {
        /* sans bornes : on ancre sur aujourd'hui */
      }
      if (this.preset === 'custom') this.preset = '30d'
      this.applyPreset(this.preset)
      this.ready = true
    },
    applyPreset(value) {
      this.preset = value
      write('df360.preset', value)
      const preset = PRESETS.find((p) => p.value === value)
      if (value === 'custom') return
      this.to = this.anchor
      if (value === 'all') this.from = this.min || addDays(this.anchor, -364)
      else this.from = addDays(this.anchor, -(preset.days - 1))
    },
    setCustom(from, to) {
      if (!from || !to) return
      this.preset = 'custom'
      this.from = from <= to ? from : to
      this.to = from <= to ? to : from
    },
    setCompare(value) {
      this.compare = value
      write('df360.compare', value)
    },
  },
})
