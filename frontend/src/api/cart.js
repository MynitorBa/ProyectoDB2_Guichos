import api from './client'

// Endpoints del carrito: obtener, agregar item por oferta_id y eliminar item por id
export const getCart = () => api.get('/cart/')
export const addItem = (oferta_id, cantidad = 1) =>
  api.post('/cart/items', { oferta_id, cantidad })
export const removeItem = (item_id) => api.delete(`/cart/items/${item_id}`)
