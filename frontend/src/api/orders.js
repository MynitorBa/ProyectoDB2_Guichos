import api from './client'

// Endpoints de pedidos (checkout, listado, detalle, factura PDF) y gestión de direcciones del usuario
// La clave de idempotencia identifica el intento de compra: reenviarla al
// reintentar (p. ej. tras un error de red) devuelve el mismo pedido y nunca
// genera un segundo cobro.
export const checkout = (data, idempotencyKey) =>
  api.post('/orders/checkout', data, { headers: { 'Idempotency-Key': idempotencyKey } })
export const getOrders = () => api.get('/orders/')
// Solicitudes que quedaron en cola mientras la base principal no respondía.
export const getQueuedOrders = () => api.get('/orders/cola')
export const getOrder = (id) => api.get(`/orders/${id}`)
export const getOrderInvoice = (id) => api.get(`/orders/${id}/invoice`, { responseType: 'blob' })
export const getAddresses = () => api.get('/addresses/')
export const createAddress = (data) => api.post('/addresses/', data)
export const updateAddress = (id, data) => api.put(`/addresses/${id}`, data)
export const deleteAddress = (id) => api.delete(`/addresses/${id}`)
