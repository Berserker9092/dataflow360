import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { calls, installFetch } from './setup'
import App from '../src/App.vue'
import router from '../src/router'
import { useAuth } from '../src/stores/auth'
import { setApiKey } from '../src/lib/api'

let warn, error, wrapper

async function boot(path, { authenticated = true } = {}) {
  localStorage.clear()
  if (authenticated) localStorage.setItem('df360.key', 'demo-key-12345')
  const pinia = createPinia()
  const auth = (await import('../src/stores/auth')).useAuth(pinia)
  auth.restore()
  await router.push(path)
  await router.isReady()
  wrapper = mount(App, { global: { plugins: [pinia, router] }, attachTo: document.body })
  for (let i = 0; i < 6; i++) await flushPromises()
  return wrapper
}

beforeEach(() => {
  warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
  error = vi.spyOn(console, 'error').mockImplementation(() => {})
  installFetch()
})
afterEach(() => {
  wrapper?.unmount()
  setApiKey('')
  vi.restoreAllMocks()
})
const noVueProblems = () => {
  expect(warn.mock.calls.map((c) => String(c[0])).filter((m) => m.includes('Vue warn'))).toEqual([])
  expect(error.mock.calls).toEqual([])
}

describe('connexion et garde de routes', () => {
  it('redirige vers /login sans clé', async () => {
    await boot('/orders', { authenticated: false })
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/orders')
    expect(wrapper.text()).toContain('Connexion à votre boutique')
  })

  it('affiche une erreur claire si la clé est refusée', async () => {
    installFetch({ failAuth: true })
    await boot('/login', { authenticated: false })
    await wrapper.find('input[type=password]').setValue('mauvaise-cle-123')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('Clé API inconnue')
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('connecte puis retourne à la page demandée', async () => {
    await boot('/login?redirect=/products', { authenticated: false })
    await wrapper.find('input[type=password]').setValue('demo-key-12345')
    await wrapper.find('form').trigger('submit')
    // la page /products est chargée à la demande (import dynamique) : on attend la navigation
    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe('/products'), { timeout: 8000 })
    expect(localStorage.getItem('df360.key')).toBe('demo-key-12345')
  })

  it('clé trop courte : message sans appel réseau', async () => {
    await boot('/login', { authenticated: false })
    await wrapper.find('input[type=password]').setValue('abc')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.text()).toContain('au moins 8 caractères')
    expect(calls).toHaveLength(0)
  })
})

describe('chaque section se charge sans erreur', () => {
  const pages = [
    ['/', "Chiffre d'affaires", '.vchart'],
    ['/orders', 'Exporter CSV', 'tbody tr'],
    ['/products', 'Top 10 produits', 'tbody tr'],
    ['/customers', 'Taux de réachat', 'tbody tr'],
    ['/customers/c32', 'Dernières commandes', 'tbody tr'],
    ['/stock', 'Sous le seuil', 'tbody tr'],
    ['/fraud', 'Alertes à traiter', '.alert-item'],
    ['/forecast', 'Détail par produit', '.vchart'],
    ['/assistant', 'Assistant IA', '.chat'],
    ['/live', 'Activité en direct', '.feed-item'],
  ]
  for (const [path, text, selector] of pages) {
    it(path, async () => {
      await boot(path)
      expect(wrapper.text()).toContain(text)
      expect(wrapper.find(selector).exists()).toBe(true)
      expect(wrapper.text()).not.toContain('fixture manquante')
      noVueProblems()
    })
  }

  it('la page inconnue affiche un 404 et le menu a 9 sections', async () => {
    await boot('/n-importe-quoi')
    expect(wrapper.text()).toContain('Page introuvable')
    wrapper.unmount()
    await boot('/')
    expect(wrapper.findAll('.nav-link[href]')).toHaveLength(9)
  })
})

describe('interactions', () => {
  it("la période modifie les requêtes et la comparaison s'affiche", async () => {
    await boot('/')
    const first = calls.find((c) => c.path === '/api/v1/reports/overview')
    expect(first.search).toContain('from=2026-05-01&to=2026-05-30&compare=prev')
    calls.length = 0
    await wrapper.findAll('.topbar .seg button').find((b) => b.text() === '7 j').trigger('click')
    await flushPromises()
    expect(calls.find((c) => c.path === '/api/v1/reports/overview').search).toContain('from=2026-05-24')
    expect(wrapper.text()).toContain('vs')
  })

  it('le thème sombre se bascule', async () => {
    await boot('/')
    await wrapper.find('button[aria-label="Changer de thème"]').trigger('click')
    expect(document.documentElement.dataset.theme).toBeTruthy()
  })

  it('décision fraude : envoie la bonne requête et retire l\'alerte', async () => {
    await boot('/fraud')
    expect(wrapper.findAll('.alert-item')).toHaveLength(3)
    calls.length = 0
    await wrapper.find('.alert-item .btn.danger').trigger('click')
    for (let i = 0; i < 4; i++) await flushPromises()
    const post = calls.find((c) => c.path === '/api/v1/fraud/decision')
    expect(post.method).toBe('POST')
    expect(JSON.parse(post.body)).toMatchObject({ action: 'BLOCK' })
    expect(wrapper.findAll('.alert-item')).toHaveLength(2)
  })

  it("l'assistant répond", async () => {
    await boot('/assistant')
    await wrapper.find('.chat-input input').setValue('Problèmes de livraison ?')
    await wrapper.find('.chat-input').trigger('submit')
    for (let i = 0; i < 4; i++) await flushPromises()
    expect(wrapper.text()).toContain('retards de livraison')
    expect(wrapper.text()).toContain('Basé sur 4 extraits')
  })

  it('le tri des commandes recharge avec le bon paramètre', async () => {
    await boot('/orders')
    calls.length = 0
    await wrapper.findAll('th').find((th) => th.text().includes('Montant')).trigger('click')
    await flushPromises()
    const req = calls.find((c) => c.path === '/api/v1/orders')
    expect(req.search).toContain('sort=total')
  })

  it('un clic sur un client ouvre sa fiche', async () => {
    await boot('/customers')
    await wrapper.find('tbody tr').trigger('click')
    for (let i = 0; i < 4; i++) await flushPromises()
    expect(router.currentRoute.value.name).toBe('customer')
  })
})
