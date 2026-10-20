import { toast } from 'sonner'
import { mensajeError, textoDe } from './errors'

// Los avisos solo pueden mostrar texto: si alguien pasa un objeto de error de la
// API, se convierte en su mensaje en lugar de romper el renderizado.
function seguro(mensaje) {
  if (mensaje == null || typeof mensaje === 'string' || typeof mensaje === 'function') return mensaje
  if (typeof mensaje === 'object' && '$$typeof' in mensaje) return mensaje // elemento de React
  if (mensaje instanceof Error || mensaje?.response || mensaje?.request) return mensajeError(mensaje)
  return textoDe(mensaje) || 'Ocurrió un error inesperado.'
}

let instalado = false

export function instalarToastSeguro() {
  if (instalado) return
  instalado = true
  for (const tipo of ['error', 'success', 'warning', 'info', 'message', 'loading']) {
    const original = toast[tipo]
    if (typeof original !== 'function') continue
    toast[tipo] = (mensaje, opciones) => original(seguro(mensaje), opciones)
  }
}

// Promesas rechazadas que ningún código atendió (por ejemplo, una llamada a la
// API sin try/catch): se muestran como aviso en vez de fallar en silencio.
export function instalarCapturaGlobal() {
  window.addEventListener('unhandledrejection', (evento) => {
    const motivo = evento.reason
    // Cancelaciones intencionales de React Query o de axios no son errores.
    if (['CanceledError', 'CancelledError', 'AbortError'].includes(motivo?.name) || motivo?.silent) return
    const mensaje = mensajeError(motivo)
    toast.error(mensaje, { id: `global:${mensaje}` })
    console.error('Promesa rechazada sin manejar:', motivo)
  })
}
