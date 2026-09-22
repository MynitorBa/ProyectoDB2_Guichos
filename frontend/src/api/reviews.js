import api from './client'

export const getReviews = (productoRef, todas = false) =>
  api.get(`/reviews/${productoRef}`, { params: { todas } })

export const createReview = (data) =>
  api.post('/reviews', data)

export const puedeOpinar = (productoRef) =>
  api.get(`/reviews/puede-opinar/${productoRef}`)

export const createReply = (resenaId, data) =>
  api.post(`/reviews/${resenaId}/respuestas`, data)

export const uploadReviewImages = (resenaId, formData) =>
  api.post(`/reviews/${resenaId}/imagenes`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })

export const getMiVendedor = () =>
  api.get('/reviews/mi-vendedor')

export const moderateReview = (resenaId, estado) =>
  api.patch(`/reviews/${resenaId}/estado`, null, { params: { estado } })

export const getFraudSummary = () =>
  api.get('/reviews/admin/fraude/resumen')

export const getFraudBombardeo = (params) =>
  api.get('/reviews/admin/fraude/bombardeo', { params })

export const getFraudSinCompra = () =>
  api.get('/reviews/admin/fraude/sin-compra')

export const getFraudCluster = (params) =>
  api.get('/reviews/admin/fraude/cluster', { params })
