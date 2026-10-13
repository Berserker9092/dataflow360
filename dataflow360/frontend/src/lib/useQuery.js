import { ref, watch, onUnmounted } from 'vue'
import { api } from './api'

// Charge une URL d'API et la recharge dès que l'URL change (période, filtres, page...).
// getUrl() peut renvoyer null pour attendre. `poll` rafraîchit toutes les N millisecondes.
export function useQuery(getUrl, { poll = 0 } = {}) {
  const data = ref(null)
  const loading = ref(true)
  const error = ref('')
  let seq = 0

  async function run(silent = false) {
    const url = getUrl()
    if (!url) return
    const id = ++seq
    if (!silent) loading.value = true
    error.value = ''
    try {
      const result = await api.get(url)
      if (id === seq) data.value = result
    } catch (e) {
      if (id === seq) error.value = e.message
    } finally {
      if (id === seq) loading.value = false
    }
  }

  watch(getUrl, () => run(false), { immediate: true })
  if (poll) {
    const timer = setInterval(() => run(true), poll)
    onUnmounted(() => clearInterval(timer))
  }
  return { data, loading, error, reload: () => run(false) }
}

// Anti-rebond pour les champs de recherche.
export function useDebounced(source, delay = 300) {
  const debounced = ref(source.value)
  let timer
  watch(source, (value) => {
    clearTimeout(timer)
    timer = setTimeout(() => (debounced.value = value), delay)
  })
  return debounced
}
