import api from './client'

export const getReviews = (productoRef, todas = false) =>
  api.get(`/reviews/${productoRef}`, { params: { todas } })

export const createReview = (data) =>
  api.post('/reviews', data)

export const updateReview = (resenaId, data) =>
  api.put(`/reviews/${resenaId}`, data)

export const puedeOpinar = (productoRef, vendedorId) =>
  api.get(`/reviews/puede-opinar/${productoRef}`, { params: { vendedor_id: vendedorId } })

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

export const recalculateFraudAlerts = () =>
  api.post('/reviews/admin/fraude/recalcular')

export const getFraudAnalysisStatus = () =>
  api.get('/reviews/admin/fraude/estado-analisis')

export const getFraudAlerts = (params = {}) =>
  api.get('/reviews/admin/fraude/alertas', { params })

export const getFraudIndicator = (regla, params = {}) =>
  api.get(`/reviews/admin/fraude/indicadores/${regla}`, { params })

export const getFraudAlertsPaginated = (params = {}) =>
  api.get('/reviews/admin/fraude/alertas-paginadas', { params })

export const updateFraudAlert = (alertaId, data) =>
  api.patch(`/reviews/admin/fraude/alertas/${alertaId}`, data)

export const getFlashFraudHistory = (params = {}) =>
  api.get('/reviews/admin/fraude/ventas-flash', { params })
