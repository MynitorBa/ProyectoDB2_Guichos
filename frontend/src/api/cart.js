import api from './client'

export const getCart = () => api.get('/cart/')
export const addItem = (oferta_id, cantidad = 1) =>
  api.post('/cart/items', { oferta_id, cantidad })
export const removeItem = (item_id) => api.delete(`/cart/items/${item_id}`)
