// Formats français ; montants en FCFA (XOF), toujours entiers.
const NBSP = '\u00a0'
const int = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 })
const dec = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 })

export const fmtInt = (n) => (n == null ? '–' : int.format(Math.round(n)))
export const fmtXof = (n) => (n == null ? '–' : `${int.format(Math.round(n))}${NBSP}FCFA`)
export const fmtDec = (n) => (n == null ? '–' : dec.format(n))

export function fmtCompact(n) {
  if (n == null) return '–'
  const abs = Math.abs(n)
  if (abs >= 1e9) return `${dec.format(n / 1e9)}${NBSP}Md`
  if (abs >= 1e6) return `${dec.format(n / 1e6)}${NBSP}M`
  if (abs >= 1e4) return `${dec.format(n / 1e3)}${NBSP}k`
  return int.format(Math.round(n))
}
export const fmtXofCompact = (n) => (n == null ? '–' : `${fmtCompact(n)}${NBSP}FCFA`)
export const fmtPct = (n, signed = false) =>
  n == null ? '–' : `${signed && n > 0 ? '+' : ''}${dec.format(n)}${NBSP}%`

const parse = (iso) => (iso && iso.length === 10 ? new Date(`${iso}T00:00:00`) : new Date(iso))
export const fmtDate = (iso) =>
  iso ? parse(iso).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' }) : '–'
export const fmtDateTime = (iso) =>
  iso
    ? parse(iso).toLocaleString('fr-FR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
    : '–'
export const fmtTime = (iso) =>
  iso ? parse(iso).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '–'
export const fmtDayShort = (iso) => parse(iso).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' })
export const fmtMonth = (iso) => parse(iso).toLocaleDateString('fr-FR', { month: 'short', year: '2-digit' })

export const STATUS_LABELS = {
  delivered: 'Livrée',
  shipped: 'Expédiée',
  approved: 'Validée',
  pending: 'En attente',
  processing: 'En préparation',
  cancelled: 'Annulée',
  failed: 'Échouée',
}
export const statusLabel = (s) => STATUS_LABELS[s] || s || '–'
export const statusTone = (s) =>
  ({ delivered: 'green', shipped: 'blue', approved: 'blue', cancelled: 'red', failed: 'red', pending: 'amber' })[s] || 'gray'
