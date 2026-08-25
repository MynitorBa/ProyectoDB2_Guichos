import api from './client'

export const getVendorStats = () => api.get('/vendor/stats')
export const getVendorOrders = (page = 1, pageSize = 20) =>
  api.get('/vendor/orders', { params: { page, page_size: pageSize } })
export const updateVendorOrderStatus = (pedidoId, estado) =>
  api.patch(`/vendor/orders/${pedidoId}/status`, { estado })
export const getVendorEstados = () => api.get('/vendor/estados')

export const getCatalogRequests = (page = 1, pageSize = 20) =>
  api.get('/vendor/catalog-requests', { params: { page, page_size: pageSize } })

export const proposeProduct = (data) =>
  api.post('/vendor/catalog-requests/products', data)

export const proposeOffer = (data) =>
  api.post('/vendor/catalog-requests/offers', data)

export const cancelCatalogRequest = (requestId) =>
  api.patch(`/vendor/catalog-requests/${requestId}/cancel`)

export const uploadRequestImage = (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/vendor/catalog-requests/images', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const deleteRequestImage = (imageId) =>
  api.delete(`/vendor/catalog-requests/images/${imageId}`)
