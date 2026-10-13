import { vi } from 'vitest'
import { h, defineComponent } from 'vue'
import fixtures from './fixtures.json'

// ECharts a besoin d'un vrai canvas : on le remplace par un composant factice qui expose l'option.
vi.mock('vue-echarts', () => ({
  default: defineComponent({
    name: 'VChart',
    props: { option: Object },
    setup(props) {
      return () => h('div', { class: 'vchart', 'data-series': String(props.option?.series?.length ?? 0) })
    },
  }),
}))

export const calls = []
export function installFetch({ failAuth = false } = {}) {
  calls.length = 0
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, init = {}) => {
      const u = new URL(url, 'http://localhost')
      let key = u.pathname
      calls.push({ path: u.pathname, search: u.search, method: init.method || 'GET', body: init.body })
      const send = (data, status = 200) => ({ ok: status < 400, status, json: async () => data, blob: async () => new Blob(['x']) })
      if (failAuth && key === '/api/v1/auth/me') return send({ detail: 'Clé API invalide' }, 401)
      if (key === '/api/v1/fraud/decision') return send({ status: 'recorded' })
      if (key.startsWith('/api/v1/forecast/') && key !== '/api/v1/forecast/products') key = '/api/v1/forecast/detail'
      if (key.startsWith('/api/v1/customers/')) key = '/api/v1/customers/c32'
      if (key === '/api/v1/orders/export') return send({})
      if (!(key in fixtures)) return send({ detail: `fixture manquante: ${key}` }, 404)
      return send(fixtures[key])
    }),
  )
}
