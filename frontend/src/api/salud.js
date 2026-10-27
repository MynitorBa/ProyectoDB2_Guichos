import api from './client'

// Estado de cada motor ('ok', 'degradado' o 'caido') para avisar al usuario.
export const getSaludMotores = () => api.get('/salud/motores')
