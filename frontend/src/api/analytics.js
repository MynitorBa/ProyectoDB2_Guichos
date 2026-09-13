import api from './client'

export const getAdminTrends = (weekStart) =>
  api.get('/analytics/admin/trends', { params: weekStart ? { semana_inicio: weekStart } : {} })

export const getVendorTrends = (weekStart) =>
  api.get('/analytics/vendor/trends', { params: weekStart ? { semana_inicio: weekStart } : {} })
