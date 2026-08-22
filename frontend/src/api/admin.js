import api from './client'

export const getAdminUsers = (page = 1, pageSize = 20) =>
  api.get('/admin/users', { params: { page, page_size: pageSize } })

export const updateUserRoles = (userId, roles) =>
  api.patch(`/admin/users/${userId}/roles`, { roles })
