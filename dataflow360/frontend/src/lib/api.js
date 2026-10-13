// Client HTTP unique : ajoute la clé API du vendeur et traduit les erreurs en messages lisibles.
const BASE = import.meta.env.VITE_API_URL || ''
let apiKey = ''
let onUnauthorized = () => {}

export const setApiKey = (key) => {
  apiKey = key || ''
}
export const setUnauthorizedHandler = (fn) => {
  onUnauthorized = fn
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function request(path, { method = 'GET', body, raw = false } = {}) {
  let res
  try {
    res = await fetch(BASE + path, {
      method,
      headers: {
        'X-Tenant-API-Key': apiKey,
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError("Impossible de joindre l'API. Vérifiez qu'elle est démarrée (dev.bat api).", 0)
  }
  if (res.status === 401) {
    onUnauthorized()
    throw new ApiError('Clé API invalide ou expirée.', 401)
  }
  if (!res.ok) {
    let detail = ''
    try {
      const data = await res.json()
      detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch {
      /* corps vide */
    }
    throw new ApiError(detail || `Erreur ${res.status}`, res.status)
  }
  return raw ? res : res.json()
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body }),
  blob: async (path) => (await request(path, { raw: true })).blob(),
}

// Construit une query string en ignorant les valeurs vides.
export function qs(params) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') search.set(key, value)
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

// Export CSV côté navigateur (séparateur ; et BOM pour Excel en français).
export function downloadCsv(rows, columns, filename) {
  const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const lines = [columns.map((c) => esc(c.label)).join(';')]
  for (const row of rows) lines.push(columns.map((c) => esc(row[c.key])).join(';'))
  downloadBlob(new Blob(['\ufeff' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' }), filename)
}
