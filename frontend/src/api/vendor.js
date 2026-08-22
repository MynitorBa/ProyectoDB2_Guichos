import api from './client'

export const getVendorStats = () => api.get('/vendor/stats')
export const getVendorOrders = (page = 1, pageSize = 20) =>
  api.get('/vendor/orders', { params: { page, page_size: pageSize } })
export const updateVendorOrderStatus = (pedidoId, estado) =>
  api.patch(`/vendor/orders/${pedidoId}/status`, { estado })
export const getVendorEstados = () => api.get('/vendor/estados')
