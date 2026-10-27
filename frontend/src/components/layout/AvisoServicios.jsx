import { useQuery } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { getSaludMotores } from '../../api/salud'
import { useAuth } from '../../context/AuthContext'

// Qué nota el usuario cuando un motor no responde. Cassandra solo afecta a los
// paneles de tendencias, así que se avisa únicamente a administradores y vendedores.
const MENSAJES = {
  mysql: 'La base de datos principal no responde: algunas funciones no están disponibles por ahora.',
  redis: 'El carrito y las ofertas flash funcionan en modo de respaldo: puedes seguir comprando, un poco más lento.',
  mongo: 'El catálogo de productos puede no cargar temporalmente.',
  elasticsearch: 'La búsqueda funciona en modo básico: sin corrección de errores ni filtros.',
  neo4j: 'Las recomendaciones y reseñas no están disponibles temporalmente.',
  cassandra: 'Los paneles de tendencias de ventas no están disponibles temporalmente.',
}
const SOLO_GESTION = new Set(['cassandra'])

export function AvisoServicios() {
  const { user } = useAuth()
  const gestiona = user?.roles?.some((rol) => rol === 'administrador' || rol === 'vendedor')
  const { data } = useQuery({
    queryKey: ['salud-motores'],
    queryFn: () => getSaludMotores().then((r) => r.data),
    refetchInterval: 30_000,
    staleTime: 10_000,
    retry: false,
    // Si el propio endpoint falla, no se muestra nada: los errores de cada
    // página ya explican lo que pasa.
    meta: { silencioso: true },
  })

  const avisos = (data?.degradados || [])
    .filter((motor) => MENSAJES[motor] && (gestiona || !SOLO_GESTION.has(motor)))
    .map((motor) => MENSAJES[motor])
  if (!avisos.length) return null

  return (
    <div role="status" className="border-b border-amber-300 bg-amber-50 text-amber-900">
      <div className="mx-auto flex max-w-7xl items-start gap-2 px-4 py-2 font-sans text-sm">
        <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
        <ul className="space-y-0.5">
          {avisos.map((texto) => <li key={texto}>{texto}</li>)}
        </ul>
      </div>
    </div>
  )
}
