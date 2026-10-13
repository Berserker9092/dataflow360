import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { fmtXof, fmtInt, fmtCompact, fmtPct, statusLabel } from '../src/lib/format'
import { addDays, diffDays } from '../src/lib/dates'
import { qs } from '../src/lib/api'
import { lineOption, hbarOption, donutOption, sparkOption } from '../src/lib/charts'
import { usePeriod } from '../src/stores/period'
import { installFetch } from './setup'

describe('formats', () => {
  it('montants en FCFA entiers avec séparateur de milliers', () => {
    expect(fmtXof(1234567.4).replace(/\s/g, ' ')).toBe('1 234 567 FCFA')
    expect(fmtInt(null)).toBe('–')
    expect(fmtCompact(2500000).replace(/\s/g, ' ')).toBe('2,5 M')
    expect(fmtPct(12.34, true).replace(/\s/g, ' ')).toBe('+12,3 %')
    expect(statusLabel('cancelled')).toBe('Annulée')
  })
})

describe('dates et requêtes', () => {
  it('calcule sans fuseau horaire', () => {
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28')
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01')
    expect(diffDays('2026-01-01', '2026-01-31')).toBe(30)
  })
  it('ignore les paramètres vides', () => {
    expect(qs({ a: 1, b: '', c: null, d: 'x y' })).toBe('?a=1&d=x+y')
    expect(qs({})).toBe('')
  })
})

describe('options de graphiques', () => {
  const labels = ['2026-05-01', '2026-05-02']
  it('courbe avec comparaison en pointillés', () => {
    const o = lineOption({ labels, series: [{ name: 'a', data: [1, 2] }, { name: 'b', data: [2, 1], dashed: true }], dark: false })
    expect(o.series).toHaveLength(2)
    expect(o.series[1].lineStyle.type).toBe('dashed')
    expect(o.legend).toBeTruthy()
  })
  it('barres, anneau et mini-courbe', () => {
    expect(hbarOption({ items: [{ label: 'p1', value: 3 }], dark: true }).series[0].type).toBe('bar')
    expect(donutOption({ items: [{ label: 'x', value: 1 }], dark: false }).series[0].type).toBe('pie')
    expect(sparkOption({ data: [1, 2, 3] }).series[0].data).toEqual([1, 2, 3])
  })
})

describe('période ancrée sur la dernière commande', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    installFetch()
  })
  it('30 jours se terminent à la date max des données', async () => {
    const p = usePeriod()
    await p.init()
    expect(p.max).toBe('2026-05-30')
    expect(p.to).toBe('2026-05-30')
    expect(p.from).toBe('2026-05-01')
    expect(p.query).toBe('from=2026-05-01&to=2026-05-30&compare=prev')
    p.applyPreset('7d')
    expect(p.from).toBe('2026-05-24')
    p.applyPreset('all')
    expect(p.from).toBe('2026-01-01')
    p.setCustom('2026-04-10', '2026-04-01')
    expect([p.from, p.to, p.preset]).toEqual(['2026-04-01', '2026-04-10', 'custom'])
  })
})
