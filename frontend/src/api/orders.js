import api from './client'

export const checkout = (data) => api.post('/orders/checkout', data)
export const getOrders = () => api.get('/orders/')
export const getOrder = (id) => api.get(`/orders/${id}`)
export const getAddresses = () => api.get('/addresses/')
export const createAddress = (data) => api.post('/addresses/', data)
