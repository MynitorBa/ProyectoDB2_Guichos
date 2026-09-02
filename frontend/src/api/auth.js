import api from './client'

// Endpoints de autenticación y perfil del usuario en sesión
export const login = (email, password) =>
  api.post('/auth/login', { email, password })

export const register = (data) =>
  api.post('/auth/register', data)

export const me = () =>
  api.get('/auth/me')

export const updateProfile = (data) =>
  api.put('/auth/me', data)

export const refreshToken = () =>
  api.post('/auth/refresh')
