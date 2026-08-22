import api from './client'

export const getAdminUsers = (page = 1, pageSize = 20) =>
  api.get('/admin/users', { params: { page, page_size: pageSize } })

export const updateUserRoles = (userId, roles) =>
  api.patch(`/admin/users/${userId}/roles`, { roles })

export const getAdminCategories = () =>
  api.get('/admin/categories')

export const createCategory = (data) =>
  api.post('/admin/categories', data)

export const updateCategorySchema = (slug, data) =>
  api.put(`/admin/categories/${slug}/schema`, data)

export const deleteCategory = (slug) =>
  api.delete(`/admin/categories/${slug}`)
