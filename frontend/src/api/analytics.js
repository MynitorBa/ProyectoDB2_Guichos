import api from './client'

export const getAdminTrends = (weekStart, comparisonWeeks = 1, onlyWithoutSales = false) =>
  api.get('/analytics/admin/trends', { params: {
    ...(weekStart ? { semana_inicio: weekStart } : {}),
    semanas_comparacion: comparisonWeeks,
    solo_sin_ventas: onlyWithoutSales,
  } })

export const getAdminProductTrend = (productRef, fromWeek, toWeek) =>
  api.get('/analytics/admin/product-trend', {
    params: { producto_ref: productRef, desde: fromWeek, hasta: toWeek },
  })

export const getVendorTrends = (weekStart, comparisonWeeks = 1, onlyWithoutSales = false) =>
  api.get('/analytics/vendor/trends', { params: {
    ...(weekStart ? { semana_inicio: weekStart } : {}),
    semanas_comparacion: comparisonWeeks,
    solo_sin_ventas: onlyWithoutSales,
  } })

export const getVendorAnalyticsProducts = (params) =>
  api.get('/analytics/vendor/products', { params })

export const getVendorProductTrend = (productRef, fromWeek, toWeek) =>
  api.get('/analytics/vendor/product-trend', {
    params: { producto_ref: productRef, desde: fromWeek, hasta: toWeek },
  })
