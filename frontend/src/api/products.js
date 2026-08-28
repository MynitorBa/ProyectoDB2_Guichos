import api from './client'

// Endpoints públicos de productos/categorías y endpoints de admin para CRUD, historial y estadísticas
export const getProducts = (params) =>
  api.get('/products', { params })

export const getAdminProducts = (params) =>
  api.get('/admin/products', { params })

export const getProduct = (id) =>
  api.get(`/products/${id}`)

export const getCategories = () =>
  api.get('/categories')

export const getCategorySchema = (slug) =>
  api.get(`/categories/${slug}/schema`)

// Admin
export const createProduct = (data) =>
  api.post('/admin/products', data)

export const updateProduct = (id, data) =>
  api.put(`/admin/products/${id}`, data)

export const deleteProduct = (id) =>
  api.delete(`/admin/products/${id}`)

export const getProductHistory = (id, params = {}) =>
  api.get(`/admin/products/${id}/history`, { params })

export const getProductStateAt = (id, fecha) =>
  api.get(`/admin/products/${id}/state-at`, { params: { fecha } })

export const getProductPriceHistory = (id, params = {}) =>
  api.get(`/admin/products/${id}/price-history`, { params })

export const getCatalogStats = () =>
  api.get('/admin/stats/catalog')
