import api from './client'

// Endpoints de notificaciones del usuario: listado, conteo de no leídas y marcado como leído
export const getNotifications = () => api.get('/notifications/')
export const getUnreadCount = () => api.get('/notifications/unread-count')
export const markAllAsRead = () => api.patch('/notifications/read-all')
export const markAsRead = (id) => api.patch(`/notifications/${id}/read`)
