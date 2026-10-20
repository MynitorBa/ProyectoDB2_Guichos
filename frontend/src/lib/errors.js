// Traduce cualquier error (de red, de la API o de JavaScript) a un mensaje legible.
// Nunca devuelve un objeto: lo que se muestra al usuario siempre es texto.

const POR_ESTADO = {
  400: 'La solicitud no es válida.',
  401: 'Tu sesión expiró. Inicia sesión de nuevo.',
  403: 'No tienes permiso para realizar esta acción.',
  404: 'No encontramos lo que buscabas.',
  408: 'El servidor tardó demasiado en responder. Intenta de nuevo.',
  409: 'La operación entra en conflicto con datos actuales. Actualiza e intenta de nuevo.',
  413: 'El archivo es demasiado grande.',
  422: 'Hay datos inválidos en el formulario.',
  429: 'Demasiadas solicitudes. Espera un momento e intenta de nuevo.',
  500: 'Ocurrió un error inesperado en el servidor. Intenta de nuevo.',
  502: 'El servidor no está disponible en este momento. Intenta de nuevo en unos segundos.',
  503: 'El servicio no está disponible temporalmente. Intenta de nuevo en unos momentos.',
  504: 'El servidor tardó demasiado en responder. Intenta de nuevo.',
}

const SIN_CONEXION = 'No se pudo conectar con el servidor. Revisa tu conexión o que TiendaYa esté iniciado.'
const SIN_RESPUESTA_A_TIEMPO = 'El servidor tardó demasiado en responder. Intenta de nuevo.'

/** Convierte cualquier valor (texto, objeto de FastAPI, lista de validaciones) en texto. */
export function textoDe(valor) {
  if (valor == null) return ''
  if (typeof valor === 'string') return valor
  if (typeof valor === 'number' || typeof valor === 'boolean') return String(valor)
  if (Array.isArray(valor)) {
    // Errores de validación de FastAPI: [{loc: [...], msg: '...'}]
    return valor
      .map((item) => {
        if (typeof item === 'string') return item
        const campo = Array.isArray(item?.loc) ? item.loc.filter((p) => p !== 'body').join('.') : ''
        const msg = textoDe(item?.msg ?? item?.message ?? item?.detail)
        return campo && msg ? `${campo}: ${msg}` : msg
      })
      .filter(Boolean)
      .join(' ')
  }
  if (typeof valor === 'object') {
    return textoDe(valor.detail ?? valor.message ?? valor.mensaje ?? valor.msg ?? '')
  }
  return ''
}

/** Mensaje para mostrar al usuario a partir de un error de axios, fetch o JavaScript. */
export function mensajeError(error, porDefecto = 'Ocurrió un error inesperado. Intenta de nuevo.') {
  if (!error) return porDefecto
  if (typeof error === 'string') return error
  if (error.mensajeUsuario) return error.mensajeUsuario
  const respuesta = error.response
  if (respuesta) {
    const texto = textoDe(respuesta.data?.detail ?? respuesta.data?.message ?? respuesta.data)
    if (texto) return texto
    return POR_ESTADO[respuesta.status] || porDefecto
  }
  if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') return SIN_RESPUESTA_A_TIEMPO
  if (error.request || error.code === 'ERR_NETWORK' || error.message === 'Network Error') return SIN_CONEXION
  return porDefecto
}

/**
 * Normaliza la respuesta de error de la API para que `data.detail` siempre sea texto.
 * Si el backend envió un objeto ({detail, code, pedido_id, ...}), sus campos se copian
 * a `data` (sin pisar los existentes) y el original queda en `data.detalle`.
 */
export function normalizarErrorApi(error) {
  const data = error?.response?.data
  if (data && typeof data === 'object' && !Array.isArray(data)) {
    const original = data.detail
    if (original && typeof original === 'object') {
      if (!Array.isArray(original)) {
        for (const [clave, valor] of Object.entries(original)) {
          if (clave !== 'detail' && !(clave in data)) data[clave] = valor
        }
      }
      data.detalle = original
      data.detail = textoDe(original) || POR_ESTADO[error.response.status] || 'Ocurrió un error.'
    }
  }
  if (error && typeof error === 'object') error.mensajeUsuario = mensajeError({ ...error, mensajeUsuario: undefined })
  return error
}
