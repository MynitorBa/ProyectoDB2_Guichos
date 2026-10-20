// Cliente mínimo de la API de TiendaYa. El laboratorio no comparte código ni
// sesión con la tienda: inicia sesión como administrador y usa los endpoints
// de diagnóstico (/admin/consistencia, /admin/checkout/saga, /admin/sync/*) y
// los de inyección de fallas, que el backend solo registra con
// FAULT_INJECTION_ENABLED=true.
export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'
export const TIENDA_URL = import.meta.env.VITE_TIENDA_URL || 'http://localhost:5173'

const CLAVE_TOKEN = 'laboratorio.token'

export class ErrorApi extends Error {
  constructor(status, detalle) {
    super(typeof detalle === 'string' ? detalle : detalle?.detail || `HTTP ${status}`)
    this.status = status
    this.detalle = detalle
  }
}

export function obtenerToken() {
  try { return localStorage.getItem(CLAVE_TOKEN) } catch { return null }
}

export function cerrarSesion() {
  try { localStorage.removeItem(CLAVE_TOKEN) } catch { /* sin almacenamiento */ }
}

async function pedir(metodo, ruta, { cuerpo, params } = {}) {
  const url = new URL(`${API_URL}${ruta}`, window.location.origin)
  Object.entries(params || {}).forEach(([k, v]) => v != null && url.searchParams.set(k, v))
  const token = obtenerToken()
  let respuesta
  try {
    respuesta = await fetch(url, {
      method: metodo,
      headers: {
        ...(cuerpo !== undefined && { 'Content-Type': 'application/json' }),
        ...(token && { Authorization: `Bearer ${token}` }),
      },
      body: cuerpo !== undefined ? JSON.stringify(cuerpo) : undefined,
    })
  } catch {
    throw new ErrorApi(0, 'No se pudo contactar al backend de TiendaYa.')
  }
  const datos = respuesta.headers.get('content-type')?.includes('json') ? await respuesta.json() : null
  if (!respuesta.ok) throw new ErrorApi(respuesta.status, datos?.detail ?? datos)
  return datos
}

export async function iniciarSesion(email, password) {
  const datos = await pedir('POST', '/auth/login', { cuerpo: { email, password } })
  try { localStorage.setItem(CLAVE_TOKEN, datos.access_token) } catch { /* solo en memoria */ }
  return datos
}

export const api = {
  fallas: () => pedir('GET', '/admin/fallas'),
  activarFalla: (punto, modo) => pedir('POST', '/admin/fallas', { cuerpo: { punto, modo } }),
  desactivarFallas: () => pedir('DELETE', '/admin/fallas'),
  modoPasarela: (modo) => pedir('POST', '/admin/fallas/pasarela', { cuerpo: { modo } }),
  recuperar: () => pedir('POST', '/admin/checkout/recuperar'),
  bitacora: (limite = 80) => pedir('GET', '/admin/checkout/saga', { params: { limite } }),
  consistencia: () => pedir('GET', '/admin/consistencia'),
  outbox: () => pedir('GET', '/admin/sync/outbox'),
  reintentarEventos: (datos = {}) => pedir('POST', '/admin/sync/outbox/reintentar', { cuerpo: datos }),
  indice: () => pedir('GET', '/admin/sync/busqueda'),
}
