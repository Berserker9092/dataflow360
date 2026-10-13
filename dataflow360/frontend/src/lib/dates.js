// Dates manipulées en texte AAAA-MM-JJ (jamais de fuseau horaire : les commandes sont « locales »).
const toUtc = (iso) => new Date(`${iso}T00:00:00Z`)
export const toIso = (date) => date.toISOString().slice(0, 10)
export const todayIso = () => {
  const d = new Date()
  return toIso(new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate())))
}
export const addDays = (iso, days) => toIso(new Date(toUtc(iso).getTime() + days * 86400000))
export const diffDays = (a, b) => Math.round((toUtc(b) - toUtc(a)) / 86400000)
