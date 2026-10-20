import { AlertTriangle, RotateCw } from 'lucide-react'
import { mensajeError } from '../lib/errors'

// Bloque para cuando una consulta falla por el servidor (servicio caído, sin
// conexión): explica el motivo real y permite reintentar, en lugar de fingir
// que el recurso no existe o que la lista está vacía.
export function EstadoError({ error, titulo = 'No pudimos cargar esta información', onReintentar, compacto = false }) {
  return (
    <div role="alert" className={compacto ? 'py-8 text-center' : 'max-w-xl mx-auto px-4 py-20 text-center'}>
      <AlertTriangle size={compacto ? 32 : 48} className="mx-auto mb-3 text-[var(--color-warning)]" aria-hidden="true" />
      <h2 className="font-display font-bold text-xl text-[var(--color-text-primary)] mb-2">{titulo}</h2>
      <p className="font-sans text-sm text-[var(--color-text-secondary)] mb-6">{mensajeError(error)}</p>
      {onReintentar && (
        <button
          type="button"
          onClick={() => onReintentar()}
          className="inline-flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--color-action)] px-4 py-2 text-sm font-medium text-white hover:opacity-90"
        >
          <RotateCw size={15} aria-hidden="true" /> Reintentar
        </button>
      )}
    </div>
  )
}

/** true si el error significa «no existe» (404) y no una falla del servicio. */
export const esNoEncontrado = (error) => error?.response?.status === 404
