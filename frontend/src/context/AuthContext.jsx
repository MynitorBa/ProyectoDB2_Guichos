import { createContext, useContext, useState, useEffect, useRef } from 'react'
import { me, refreshToken } from '../api/auth'
import { queryClient } from '../lib/queryClient'

const AuthContext = createContext(null)

const REFRESH_BEFORE_MS = 5 * 60 * 1000 // renovar 5 min antes de expirar

function getTokenExpiry(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.exp * 1000
  } catch {
    return null
  }
}

// Contexto global de autenticación: expone user, loading, signIn, signOut y updateUser
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const refreshTimer = useRef(null)

  function scheduleRefresh(token) {
    clearTimeout(refreshTimer.current)
    const expiry = getTokenExpiry(token)
    if (!expiry) return
    const delay = expiry - Date.now() - REFRESH_BEFORE_MS
    if (delay <= 0) return
    refreshTimer.current = setTimeout(async () => {
      try {
        const res = await refreshToken()
        const newToken = res.data.access_token
        localStorage.setItem('token', newToken)
        scheduleRefresh(newToken)
      } catch {
        // Si el refresh falla el interceptor de axios manejará el siguiente 401
      }
    }, delay)
  }

  // Al montar, verifica si ya hay token guardado y carga los datos del usuario
  useEffect(() => {
    const token = localStorage.getItem('token')
    if (token) {
      me()
        .then((r) => { setUser(r.data); scheduleRefresh(token) })
        .catch(() => localStorage.removeItem('token'))
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
    return () => clearTimeout(refreshTimer.current)
  }, [])

  const signIn = (token, userData) => {
    localStorage.setItem('token', token)
    setUser(userData)
    scheduleRefresh(token)
  }

  // Al cerrar sesión limpia también el caché de React Query para evitar datos residuales
  const signOut = () => {
    clearTimeout(refreshTimer.current)
    localStorage.removeItem('token')
    setUser(null)
    queryClient.clear()
  }

  const updateUser = (userData) => {
    setUser(userData)
  }

  return (
    <AuthContext.Provider value={{ user, loading, signIn, signOut, updateUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
