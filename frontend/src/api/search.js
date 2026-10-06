import api from './client'

// Búsqueda de productos sobre Elasticsearch (con respaldo en MongoDB del lado del servidor).
// Los filtros repetibles viajan como claves repetidas (?vendedor=a&vendedor=b,
// ?attr.talla=M&attr.talla=L), que es lo que espera FastAPI; por eso se arma la
// query a mano en lugar de usar la serialización de arreglos de axios (vendedor[]=a).
function toSearchParams({ atributos = {}, vendedores = [], ...rest }) {
  const params = new URLSearchParams()
  Object.entries(rest).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '' && value !== false) {
      params.append(key, value)
    }
  })
  vendedores.forEach((v) => params.append('vendedor', v))
  Object.entries(atributos).forEach(([nombre, valores]) => {
    valores.forEach((valor) => params.append(`attr.${nombre}`, valor))
  })
  return params
}

export const searchProducts = (filters) =>
  api.get('/search', { params: toSearchParams(filters) })

export const suggestProducts = (q, limite = 6) =>
  api.get('/search/suggest', { params: { q, limite } })
