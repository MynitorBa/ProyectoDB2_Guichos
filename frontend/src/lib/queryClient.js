import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { mensajeError } from './errors'

// Solo se reintenta lo que puede ser pasajero (red, 502, 504). Un 4xx no se
// arregla reintentando y un 503 significa que el servidor ya confirmó que el
// servicio está caído: repetir solo haría esperar más al usuario.
function reintentar(intentos, error) {
  const estado = error?.response?.status
  if (estado && ![502, 504].includes(estado)) return false
  return intentos < 1
}

// Fallas del servidor o de la red (no errores de negocio como 404 o 409).
function esFallaDeServicio(error) {
  const estado = error?.response?.status
  return !error?.response || estado >= 500
}

// Instancia global de React Query: datos frescos por 30 segundos y avisos de error
// centralizados para que ninguna falla de servicio pase desapercibida.
export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error, query) => {
      // Un 503 indica que un motor cayó: se actualiza el aviso de servicios sin esperar su sondeo.
      if (error?.response?.status === 503 && query.queryKey[0] !== 'salud-motores') {
        queryClient.invalidateQueries({ queryKey: ['salud-motores'] })
      }
      if (query.meta?.silencioso || !esFallaDeServicio(error)) return
      const mensaje = mensajeError(error)
      // Un mismo id evita apilar el mismo aviso cuando fallan varias consultas a la vez.
      toast.error(mensaje, { id: `consulta:${mensaje}` })
    },
  }),
  mutationCache: new MutationCache({
    onError: (error, _variables, _context, mutation) => {
      if (error?.response?.status === 503) queryClient.invalidateQueries({ queryKey: ['salud-motores'] })
      // Si la acción ya maneja su error, no se duplica el aviso.
      if (mutation.options.onError || mutation.meta?.silencioso) return
      toast.error(mensajeError(error, 'No se pudo completar la acción.'))
    },
  }),
  defaultOptions: {
    queries: { retry: reintentar, staleTime: 30_000 },
    mutations: { retry: false },
  },
})
