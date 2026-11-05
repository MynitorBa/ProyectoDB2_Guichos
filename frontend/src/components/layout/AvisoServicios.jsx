import { useQuery } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { getSaludMotores } from '../../api/salud'
import { useAuth } from '../../context/AuthContext'

const MENSAJES_COMPRADOR = {
  mysql: 'Puedes seguir navegando. Si dejas una solicitud de compra en cola, aún no será un pedido confirmado y no se realizará ningún cobro hasta procesarla.',
  mongo: 'El catálogo puede mostrar información con un breve retraso.',
  elasticsearch: 'La búsqueda está temporalmente limitada. Puedes seguir navegando por el catálogo.',
}
const MENSAJES_VENDEDOR = {
  ...MENSAJES_COMPRADOR,
  mongo: 'El catálogo puede mostrar información atrasada y la edición de productos está temporalmente limitada.',
  cassandra: 'Las tendencias pueden mostrar información con un breve retraso.',
  neo4j: 'Las nuevas señales de fraude están pendientes de análisis. Las existentes siguen disponibles.',
}
const MENSAJES_ADMIN = {
  ...MENSAJES_VENDEDOR,
  mysql: 'MySQL no responde. Las solicitudes nuevas quedan en cola, sin pedido confirmado ni cobro. Revise el historial de planes B al recuperarse.',
  redis: 'Redis no responde. Carrito y reservas utilizan su respaldo.',
  mongo: 'MongoDB no responde. El catálogo usa la copia de MySQL y la edición está limitada.',
  elasticsearch: 'Elasticsearch no responde. La búsqueda usa el modo básico.',
  neo4j: 'Neo4j no responde. El análisis nuevo de fraude queda pendiente. Los expedientes históricos siguen disponibles.',
  cassandra: 'Cassandra no responde. Las tendencias usan el respaldo analítico MySQL.',
  embeddings: 'El servicio de embeddings no responde. Se mantiene la búsqueda textual.',
}

export function AvisoServicios() {
  const { user } = useAuth()
  const mensajes = user?.roles?.includes('administrador') ? MENSAJES_ADMIN
    : user?.roles?.includes('vendedor') ? MENSAJES_VENDEDOR : MENSAJES_COMPRADOR
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
    .filter((motor) => mensajes[motor])
    .map((motor) => mensajes[motor])
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
