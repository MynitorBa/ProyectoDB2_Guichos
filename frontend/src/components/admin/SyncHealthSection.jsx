import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Database, Search as SearchIcon, BarChart2, GitBranch, Zap, RefreshCw, RotateCw, PauseCircle, CheckCircle2,
} from 'lucide-react'
import { toast } from 'sonner'

import { getSearchIndexStatus, getSyncOutbox, reindexSearch, retrySyncEvents } from '../../api/admin'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Skeleton } from '../ui/skeleton'
import { cn } from '../../lib/utils'

// El backend guarda fechas UTC sin zona; se interpretan como UTC para mostrarlas en hora local.
function horaLocal(iso) {
  if (!iso) return '—'
  const fecha = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`)
  return fecha.toLocaleString('es-GT', { dateStyle: 'short', timeStyle: 'medium' })
}

function duracion(segundos) {
  if (segundos == null) return '—'
  if (segundos < 60) return `${Math.round(segundos)} s`
  if (segundos < 3600) return `${Math.round(segundos / 60)} min`
  return `${(segundos / 3600).toFixed(1)} h`
}

function errorDe(err, porDefecto) {
  const detalle = err?.response?.data?.detail
  return (typeof detalle === 'string' ? detalle : detalle?.detail) || porDefecto
}

function Panel({ titulo, descripcion, acciones, children, className }) {
  return (
    <section className={cn('bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5', className)}>
      <div className="flex items-start justify-between gap-4 mb-4 flex-wrap">
        <div>
          <h3 className="font-display font-semibold text-base text-[var(--color-text-primary)]">{titulo}</h3>
          {descripcion && <p className="font-sans text-xs text-[var(--color-text-muted)] mt-0.5 max-w-2xl">{descripcion}</p>}
        </div>
        {acciones && <div className="flex gap-2 flex-wrap">{acciones}</div>}
      </div>
      {children}
    </section>
  )
}

// ── Salud de la sincronización ────────────────────────────────────────────────

const DESTINOS = {
  mongo:     { label: 'MongoDB',       detalle: 'Proyección del catálogo e historial', Icon: Database },
  busqueda:  { label: 'Elasticsearch', detalle: 'Índice de búsqueda',                  Icon: SearchIcon },
  cassandra: { label: 'Cassandra',     detalle: 'Analítica de ventas',                 Icon: BarChart2 },
  neo4j:     { label: 'Neo4j',         detalle: 'Compras verificadas para reseñas',    Icon: GitBranch },
  redis:     { label: 'Redis',         detalle: 'Limpieza de carritos y reservas',     Icon: Zap },
}

function estadoDestino(d) {
  if (d.fallido > 0) return { texto: 'Con eventos fallidos', variant: 'error' }
  if (d.error > 0 || d.en_pausa) return { texto: 'Reintentando', variant: 'warning' }
  if (d.pendiente + d.procesando > 0) return { texto: 'Sincronizando', variant: 'action' }
  return { texto: 'Al día', variant: 'success' }
}

function TarjetaDestino({ destino }) {
  const meta = DESTINOS[destino.destino]
  const estado = estadoDestino(destino)
  const { Icon } = meta
  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <Icon size={16} className="text-[var(--color-action)]" />
          <div>
            <p className="font-sans font-semibold text-sm text-[var(--color-text-primary)]">{meta.label}</p>
            <p className="font-sans text-[11px] text-[var(--color-text-muted)]">{meta.detalle}</p>
          </div>
        </div>
        {destino.en_pausa && <PauseCircle size={15} className="text-amber-600" aria-label="Destino en pausa" />}
      </div>
      <Badge variant={estado.variant}>{estado.texto}</Badge>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 font-sans text-xs">
        <dt className="text-[var(--color-text-muted)]">Pendientes</dt><dd className="font-mono text-right">{destino.pendiente + destino.procesando}</dd>
        <dt className="text-[var(--color-text-muted)]">Con error</dt><dd className="font-mono text-right">{destino.error}</dd>
        <dt className="text-[var(--color-text-muted)]">Fallidos</dt><dd className="font-mono text-right">{destino.fallido}</dd>
        <dt className="text-[var(--color-text-muted)]">Procesados</dt><dd className="font-mono text-right">{destino.procesado}</dd>
        <dt className="text-[var(--color-text-muted)]">Más antiguo</dt><dd className="font-mono text-right">{duracion(destino.pendiente_mas_antiguo_segundos)}</dd>
      </dl>
    </div>
  )
}

export function SyncHealthSection() {
  const queryClient = useQueryClient()
  const outbox = useQuery({
    queryKey: ['admin-sync-outbox'],
    queryFn: () => getSyncOutbox().then((r) => r.data),
    refetchInterval: 5000,
  })
  const indice = useQuery({
    queryKey: ['admin-sync-busqueda'],
    queryFn: () => getSearchIndexStatus().then((r) => r.data),
    refetchInterval: 10000,
  })
  const refrescar = () => {
    queryClient.invalidateQueries({ queryKey: ['admin-sync-outbox'] })
    queryClient.invalidateQueries({ queryKey: ['admin-sync-busqueda'] })
  }
  const reintentar = useMutation({
    mutationFn: retrySyncEvents,
    onSuccess: (r) => { toast.success(`${r.data.reintentados} evento(s) devueltos a la cola.`); refrescar() },
    onError: (err) => toast.error(errorDe(err, 'No se pudo reintentar.')),
  })
  const reindexar = useMutation({
    mutationFn: reindexSearch,
    onSuccess: (r) => { toast.success(`Índice actualizado: ${r.data.indexados} indexados, ${r.data.eliminados} eliminados.`); refrescar() },
    onError: (err) => toast.error(errorDe(err, 'No se pudo reindexar.')),
  })

  const destinos = outbox.data?.destinos || []
  const problemas = outbox.data?.problemas || []
  const idx = indice.data

  return (
    <div className="space-y-6">
      <p className="font-sans text-sm text-[var(--color-text-secondary)] max-w-3xl">
        MySQL es la fuente de verdad. Cada cambio se encola en el outbox dentro de la misma transacción y un
        worker lo proyecta, con reintentos, hacia cada componente. Aquí se ve cuánto falta por sincronizar en cada uno.
      </p>

      <Panel
        titulo="Outbox por destino"
        descripcion="Se actualiza cada 5 s. Un destino caído no detiene a los demás: sus eventos esperan con backoff exponencial."
        acciones={<Button size="sm" variant="secondary" onClick={refrescar}><RefreshCw size={13} /> Actualizar</Button>}
      >
        {outbox.isLoading ? (
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-44" />)}</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            {destinos.map((d) => <TarjetaDestino key={d.destino} destino={d} />)}
          </div>
        )}
      </Panel>

      <Panel
        titulo="Índice de búsqueda"
        descripcion="Proyección del catálogo en Elasticsearch. Una reconciliación periódica (cada 10 min) corrige lo que el outbox no alcanzó a cubrir."
        acciones={<>
          <Button size="sm" variant="secondary" loading={reindexar.isPending} onClick={() => reindexar.mutate(false)}>Reindexar diferencias</Button>
          <Button size="sm" variant="secondary" loading={reindexar.isPending} onClick={() => reindexar.mutate(true)}>Reindexar todo</Button>
        </>}
      >
        {!idx ? <Skeleton className="h-10" /> : idx.disponible ? (
          <div className="flex flex-wrap items-center gap-x-8 gap-y-2 font-sans text-sm">
            <span><span className="text-[var(--color-text-muted)]">Índice: </span><span className="font-mono">{idx.indice}</span></span>
            <span><span className="text-[var(--color-text-muted)]">Documentos: </span><span className="font-mono">{idx.documentos}</span></span>
            <span><span className="text-[var(--color-text-muted)]">Productos activos: </span><span className="font-mono">{idx.productos_activos}</span></span>
            <Badge variant={idx.documentos === idx.productos_activos ? 'success' : 'warning'}>
              {idx.documentos === idx.productos_activos ? 'Completo' : 'Desfasado'}
            </Badge>
          </div>
        ) : (
          <p className="font-sans text-sm text-amber-800">
            Elasticsearch no responde: la búsqueda funciona en modo degradado sobre MongoDB. ({idx.error})
          </p>
        )}
      </Panel>

      <Panel
        titulo="Eventos con problemas"
        descripcion="Eventos en error (se reintentarán solos) o fallidos (agotaron sus 10 intentos y necesitan un reintento manual)."
        acciones={problemas.length > 0 && (
          <Button size="sm" variant="secondary" loading={reintentar.isPending} onClick={() => reintentar.mutate({})}>
            <RotateCw size={13} /> Reintentar todos
          </Button>
        )}
      >
        {problemas.length === 0 ? (
          <p className="font-sans text-sm text-[var(--color-text-muted)] flex items-center gap-2">
            <CheckCircle2 size={15} className="text-[var(--color-success)]" /> No hay eventos con problemas.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm font-sans">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)]">
                  <th className="py-2 pr-3">Evento</th><th className="py-2 pr-3">Destino</th><th className="py-2 pr-3">Estado</th>
                  <th className="py-2 pr-3">Intentos</th><th className="py-2 pr-3">Último error</th><th className="py-2 pr-3">Próximo intento</th><th />
                </tr>
              </thead>
              <tbody>
                {problemas.map((e) => (
                  <tr key={e.id} className="border-b border-[var(--color-border)] last:border-0 align-top">
                    <td className="py-2 pr-3"><span className="font-mono text-xs">{e.tipo_evento}</span><br /><span className="text-[11px] text-[var(--color-text-muted)]">{e.agregado}</span></td>
                    <td className="py-2 pr-3">{DESTINOS[e.destino]?.label || e.destino}</td>
                    <td className="py-2 pr-3"><Badge variant={e.estado === 'fallido' ? 'error' : 'warning'}>{e.estado}</Badge></td>
                    <td className="py-2 pr-3 font-mono">{e.intentos}</td>
                    <td className="py-2 pr-3 max-w-xs"><span className="text-xs text-[var(--color-text-secondary)] line-clamp-2" title={e.ultimo_error}>{e.ultimo_error}</span></td>
                    <td className="py-2 pr-3 text-xs">{horaLocal(e.siguiente_intento_en)}</td>
                    <td className="py-2"><Button size="sm" variant="ghost" onClick={() => reintentar.mutate({ evento_id: e.id })}><RotateCw size={13} /></Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}
