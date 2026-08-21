import api from './client'

export const getProducts = (params) =>
  api.get('/products', { params })

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

export const getProductHistory = (id) =>
  api.get(`/admin/products/${id}/history`)

export const getProductStateAt = (id, fecha) =>
  api.get(`/admin/products/${id}/state-at`, { params: { fecha } })

export const getCatalogStats = () =>
  api.get('/admin/stats/catalog')
