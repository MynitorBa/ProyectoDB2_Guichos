import { createContext, useContext, useState, useEffect } from 'react'
import { me } from '../api/auth'
import { queryClient } from '../lib/queryClient'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (token) {
      me()
        .then((r) => setUser(r.data))
        .catch(() => localStorage.removeItem('token'))
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  const signIn = (token, userData) => {
    localStorage.setItem('token', token)
    setUser(userData)
  }

  const signOut = () => {
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
