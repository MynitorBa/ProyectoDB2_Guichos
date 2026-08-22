import api from './client'

export const getAdminUsers = (page = 1, pageSize = 20) =>
  api.get('/admin/users', { params: { page, page_size: pageSize } })

export const getAdminVendors = () =>
  api.get('/admin/vendors')

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

export const uploadAdminImage = (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/admin/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const getAdminSalesStats = () =>
  api.get('/admin/sales/stats')

export const getAdminSales = (page = 1, pageSize = 20) =>
  api.get('/admin/sales', { params: { page, page_size: pageSize } })

export const exportAdminSalesExcel = () =>
  api.get('/admin/sales/export', { responseType: 'blob' })

export const getAdminOrders = (page = 1, pageSize = 20, estado = null) =>
  api.get('/admin/orders', { params: { page, page_size: pageSize, ...(estado && { estado }) } })

export const updateAdminOrderStatus = (pedidoId, estado) =>
  api.patch(`/admin/orders/${pedidoId}/status`, { estado })

export const setVendorProfile = (userId, data) =>
  api.post(`/admin/users/${userId}/vendor-profile`, data)
