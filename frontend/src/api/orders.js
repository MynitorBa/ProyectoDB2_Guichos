import api from './client'

// Endpoints de pedidos (checkout, listado, detalle, factura PDF) y gestión de direcciones del usuario
export const checkout = (data) => api.post('/orders/checkout', data)
export const getOrders = () => api.get('/orders/')
export const getOrder = (id) => api.get(`/orders/${id}`)
export const getOrderInvoice = (id) => api.get(`/orders/${id}/invoice`, { responseType: 'blob' })
export const getAddresses = () => api.get('/addresses/')
export const createAddress = (data) => api.post('/addresses/', data)
export const updateAddress = (id, data) => api.put(`/addresses/${id}`, data)
export const deleteAddress = (id) => api.delete(`/addresses/${id}`)
