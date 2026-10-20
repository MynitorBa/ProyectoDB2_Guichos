import axios from 'axios'
import { normalizarErrorApi } from '../lib/errors'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api/v1',
  headers: { 'Content-Type': 'application/json' },
  // Ninguna petición queda colgada indefinidamente si un servicio no responde.
  timeout: 30_000,
})

// Adjunta el JWT en cada request si existe en localStorage
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Normaliza los errores (detail siempre es texto) y, si el servidor devuelve 401
// en una ruta protegida, limpia el token y redirige al login.
api.interceptors.response.use(
  (res) => res,
  (error) => {
    normalizarErrorApi(error)
    const esLogin = error.config?.url?.includes('/auth/login')
    if (error.response?.status === 401 && !esLogin) {
      localStorage.removeItem('token')
      if (window.location.pathname !== '/login') window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default api
