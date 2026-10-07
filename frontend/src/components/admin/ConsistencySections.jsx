import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Database, Search as SearchIcon, BarChart2, GitBranch, Zap, RefreshCw, RotateCw, PauseCircle,
  CheckCircle2, XCircle, MinusCircle, ShieldCheck, Activity, CreditCard, FlaskConical, PlayCircle,
} from 'lucide-react'
import { toast } from 'sonner'

import {
  clearFaults, getConsistency, getFaults, getSagaLog, getSearchIndexStatus, getSyncOutbox,
  reindexSearch, retrySyncEvents, runCheckoutRecovery, setFault, setGatewayMode,
} from '../../api/admin'
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

// ── Laboratorio de fallas ─────────────────────────────────────────────────────

const MODOS_PASARELA = [
  { modo: 'aprobar', label: 'Aprobar', detalle: 'Cobra y responde aprobado.' },
  { modo: 'rechazar', label: 'Rechazar', detalle: 'Fondos insuficientes: el pedido se compensa.' },
  { modo: 'timeout', label: 'Timeout', detalle: 'Cobra pero no responde a tiempo: pago en verificación.' },
  { modo: 'cobrar_y_fallar', label: 'Cobrar y fallar', detalle: 'Cobra y responde 500: el reintento idempotente lo resuelve.' },
  { modo: 'error_antes', label: 'Error 503', detalle: 'No cobra ni responde: verificación y luego compensación.' },
]

const RESULTADO_COLOR = {
  ok: 'success', aprobado: 'success', rechazado: 'error', no_encontrado: 'warning',
  desconocido: 'warning', no_enviado: 'warning', pendiente: 'warning', reembolsado: 'default',
}

function Invariantes() {
  const consistencia = useQuery({
    queryKey: ['admin-consistencia'],
    queryFn: () => getConsistency().then((r) => r.data),
    refetchInterval: 15000,
  })
  const datos = consistencia.data
  return (
    <Panel
      titulo="Invariantes de consistencia"
      descripcion="Propiedades que el sistema debe cumplir siempre, incluso después de una falla. Se verifican contra MySQL, la pasarela, MongoDB y Elasticsearch."
      acciones={<Button size="sm" variant="secondary" loading={consistencia.isFetching} onClick={() => consistencia.refetch()}>
        <ShieldCheck size={13} /> Verificar ahora
      </Button>}
    >
      {!datos ? <Skeleton className="h-40" /> : (
        <div className="space-y-2">
          <p className={cn('font-sans text-sm font-semibold', datos.ok ? 'text-[var(--color-success)]' : 'text-[var(--color-error)]')}>
            {datos.ok ? 'Todos los invariantes se cumplen.' : 'Hay invariantes violados.'}
            <span className="font-normal text-xs text-[var(--color-text-muted)] ml-2">{horaLocal(datos.generado_en)}</span>
          </p>
          <ul className="divide-y divide-[var(--color-border)]">
            {datos.invariantes.map((inv) => (
              <li key={inv.id} className="py-2 flex gap-3">
                {inv.ok === true && <CheckCircle2 size={16} className="text-[var(--color-success)] shrink-0 mt-0.5" />}
                {inv.ok === false && <XCircle size={16} className="text-[var(--color-error)] shrink-0 mt-0.5" />}
                {inv.ok === null && <MinusCircle size={16} className="text-[var(--color-text-muted)] shrink-0 mt-0.5" />}
                <div className="min-w-0 font-sans">
                  <p className="text-sm text-[var(--color-text-primary)]"><span className="font-mono text-xs text-[var(--color-text-muted)] mr-2">{inv.id}</span>{inv.titulo}</p>
                  <p className="text-xs text-[var(--color-text-muted)]">{inv.detalle}</p>
                  {inv.nota && <p className="text-xs text-amber-700">Nota: {inv.nota}</p>}
                  {inv.ejemplos?.length > 0 && (
                    <pre className="mt-1 text-[11px] font-mono bg-[var(--color-background)] rounded p-2 overflow-x-auto">
                      {inv.ejemplos.map((e) => JSON.stringify(e)).join('\n')}
                    </pre>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  )
}

function BitacoraSaga() {
  const bitacora = useQuery({
    queryKey: ['admin-saga'],
    queryFn: () => getSagaLog({ limite: 60 }).then((r) => r.data),
    refetchInterval: 3000,
  })
  const pasos = bitacora.data || []
  return (
    <Panel
      titulo="Bitácora de la saga del checkout"
      descripcion="Cada transición de cada compra: reserva → cobro → confirmación o compensación, incluidas las que resuelven el reconciliador y el recolector. Se actualiza cada 3 s."
    >
      {pasos.length === 0 ? (
        <p className="font-sans text-sm text-[var(--color-text-muted)]">Todavía no hay compras registradas con la saga.</p>
      ) : (
        <div className="overflow-x-auto max-h-[28rem] overflow-y-auto">
          <table className="w-full text-sm font-sans">
            <thead className="sticky top-0 bg-[var(--color-surface)]">
              <tr className="text-left text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)]">
                <th className="py-2 pr-3">Hora</th><th className="py-2 pr-3">Pedido</th><th className="py-2 pr-3">Paso</th>
                <th className="py-2 pr-3">Resultado</th><th className="py-2 pr-3">Pedido ahora</th><th className="py-2 pr-3">Pago ahora</th>
              </tr>
            </thead>
            <tbody>
              {pasos.map((p) => (
                <tr key={p.id} className="border-b border-[var(--color-border)] last:border-0">
                  <td className="py-1.5 pr-3 text-xs whitespace-nowrap">{horaLocal(p.creado_en)}</td>
                  <td className="py-1.5 pr-3 font-mono">#{p.pedido_id}</td>
                  <td className="py-1.5 pr-3">{p.paso}</td>
                  <td className="py-1.5 pr-3"><Badge variant={RESULTADO_COLOR[p.resultado] || 'default'}>{p.resultado}</Badge></td>
                  <td className="py-1.5 pr-3 text-xs">{p.pedido_estado}{p.motivo_cancelacion && <span className="text-[var(--color-text-muted)]"> · {p.motivo_cancelacion}</span>}</td>
                  <td className="py-1.5 pr-3 text-xs">{p.pago_estado}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}

export function FaultLabSection() {
  const queryClient = useQueryClient()
  const [ultimaRecuperacion, setUltimaRecuperacion] = useState(null)
  const fallas = useQuery({
    queryKey: ['admin-fallas'],
    queryFn: () => getFaults().then((r) => r.data),
    refetchInterval: 5000,
  })
  const refrescar = () => queryClient.invalidateQueries({ queryKey: ['admin-fallas'] })
  const cambiarModo = useMutation({
    mutationFn: setGatewayMode,
    onSuccess: (_, modo) => { toast.success(`Pasarela en modo «${modo}».`); refrescar() },
    onError: (err) => toast.error(errorDe(err, 'No se pudo cambiar el modo de la pasarela.')),
  })
  const cambiarFalla = useMutation({
    mutationFn: ({ punto, modo }) => setFault(punto, modo),
    onSuccess: refrescar,
    onError: (err) => toast.error(errorDe(err, 'No se pudo configurar el punto de falla.')),
  })
  const limpiar = useMutation({ mutationFn: clearFaults, onSuccess: refrescar })
  const recuperar = useMutation({
    mutationFn: runCheckoutRecovery,
    onSuccess: (r) => {
      setUltimaRecuperacion({ ...r.data, en: new Date().toISOString() })
      queryClient.invalidateQueries({ queryKey: ['admin-saga'] })
      queryClient.invalidateQueries({ queryKey: ['admin-consistencia'] })
    },
    onError: (err) => toast.error(errorDe(err, 'No se pudo ejecutar la recuperación.')),
  })

  const datos = fallas.data
  const habilitada = datos?.habilitada
  const modoActual = datos?.pasarela?.modo

  return (
    <div className="space-y-6">
      <p className="font-sans text-sm text-[var(--color-text-secondary)] max-w-3xl">
        Provoca fallas reales en el checkout distribuido y observa cómo el sistema se recupera: la saga compensa,
        los reintentos idempotentes evitan cobros dobles y los invariantes confirman que no quedó nada inconsistente.
      </p>

      {datos && !habilitada && (
        <div role="status" className="rounded-[var(--radius-md)] border border-amber-300 bg-amber-50 px-4 py-3 font-sans text-sm text-amber-900">
          La inyección de fallas está deshabilitada. Para usar este laboratorio en desarrollo agrega{' '}
          <code className="font-mono bg-amber-100 px-1 rounded">FAULT_INJECTION_ENABLED=true</code>{' '}
          a <code className="font-mono bg-amber-100 px-1 rounded">backend/.env</code> y reinicia el backend.
          {' '}La bitácora y los invariantes funcionan igualmente.
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <Panel
          titulo="Pasarela de pagos simulada"
          descripcion="Sistema externo e independiente de MySQL. Su comportamiento determina el desenlace de cada compra."
        >
          {!datos ? <Skeleton className="h-40" /> : !datos.pasarela ? (
            <p className="font-sans text-sm text-[var(--color-error)]">
              La pasarela simulada no responde en :8001. Inicia el sistema con <code className="font-mono">start-dev.ps1</code>.
            </p>
          ) : (
            <div className="space-y-2">
              {MODOS_PASARELA.map((m) => (
                <button
                  key={m.modo}
                  type="button"
                  disabled={!habilitada || cambiarModo.isPending}
                  onClick={() => cambiarModo.mutate(m.modo)}
                  aria-pressed={modoActual === m.modo}
                  className={cn(
                    'w-full flex items-center gap-3 text-left px-3 py-2 rounded-[var(--radius-md)] border transition-colors disabled:opacity-60 disabled:cursor-not-allowed',
                    modoActual === m.modo ? 'border-[var(--color-action)] bg-[var(--color-action)]/8' : 'border-[var(--color-border)] hover:border-[var(--color-action)]/40'
                  )}
                >
                  <CreditCard size={15} className={modoActual === m.modo ? 'text-[var(--color-action)]' : 'text-[var(--color-text-muted)]'} />
                  <span className="flex-1">
                    <span className="block font-sans text-sm font-semibold text-[var(--color-text-primary)]">{m.label}</span>
                    <span className="block font-sans text-xs text-[var(--color-text-muted)]">{m.detalle}</span>
                  </span>
                  {modoActual === m.modo && <Badge variant="action">Activo</Badge>}
                </button>
              ))}
            </div>
          )}
        </Panel>

        <Panel
          titulo="Puntos de falla"
          descripcion="Simulan que el proceso cae en un punto exacto del flujo. «Una vez» se desactiva tras dispararse."
          acciones={habilitada && <Button size="sm" variant="secondary" onClick={() => limpiar.mutate()}>Desactivar todos</Button>}
        >
          {!datos ? <Skeleton className="h-40" /> : (
            <ul className="space-y-2">
              {datos.puntos.map((p) => (
                <li key={p.punto} className="flex items-center gap-3 rounded-[var(--radius-md)] border border-[var(--color-border)] px-3 py-2">
                  <FlaskConical size={15} className={p.modo ? 'text-[var(--color-error)]' : 'text-[var(--color-text-muted)]'} />
                  <div className="flex-1 min-w-0">
                    <p className="font-mono text-xs text-[var(--color-text-primary)]">{p.punto}</p>
                    <p className="font-sans text-xs text-[var(--color-text-muted)]">{p.descripcion}{p.disparos > 0 && ` · disparada ${p.disparos} vez/veces`}</p>
                  </div>
                  <div className="flex rounded-[var(--radius-md)] border border-[var(--color-border)] overflow-hidden shrink-0" role="group" aria-label={`Modo de ${p.punto}`}>
                    {[['off', 'Off'], ['una_vez', 'Una vez'], ['siempre', 'Siempre']].map(([modo, label]) => {
                      const activo = (p.modo || 'off') === modo
                      return (
                        <button
                          key={modo}
                          type="button"
                          disabled={!habilitada}
                          aria-pressed={activo}
                          onClick={() => cambiarFalla.mutate({ punto: p.punto, modo })}
                          className={cn('px-2 py-1 font-sans text-[11px] disabled:opacity-50',
                            activo ? (modo === 'off' ? 'bg-[var(--color-border)] font-semibold' : 'bg-[var(--color-error)] text-white font-semibold') : 'hover:bg-[var(--color-border)]/60')}
                        >
                          {label}
                        </button>
                      )
                    })}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <Panel
        titulo="Recuperación del checkout"
        descripcion="El worker la ejecuta cada 5 s: el reconciliador consulta a la pasarela los pagos en verificación y el recolector atiende los pedidos cuya reserva venció a mitad de la saga."
        acciones={<Button size="sm" loading={recuperar.isPending} onClick={() => recuperar.mutate()}>
          <PlayCircle size={14} /> Ejecutar ahora
        </Button>}
      >
        {ultimaRecuperacion ? (
          <div className="font-sans text-sm space-y-1">
            <p className="text-[var(--color-text-muted)] text-xs">{horaLocal(ultimaRecuperacion.en)}</p>
            {['reconciliador', 'recolector'].map((tarea) => {
              const resumen = ultimaRecuperacion[tarea] || {}
              const entradas = Object.entries(resumen)
              return (
                <p key={tarea}>
                  <span className="font-semibold capitalize">{tarea}: </span>
                  {entradas.length ? entradas.map(([k, v]) => `${v} ${k.replace('_', ' ')}`).join(', ') : 'nada pendiente'}
                </p>
              )
            })}
          </div>
        ) : (
          <p className="font-sans text-sm text-[var(--color-text-muted)] flex items-center gap-2">
            <Activity size={14} /> Ejecuta la recuperación para ver qué resolvió.
          </p>
        )}
      </Panel>

      <Invariantes />
      <BitacoraSaga />

      <p className="font-sans text-xs text-[var(--color-text-muted)]">
        Para ver el estado de la sincronización con cada componente abre <Link className="text-[var(--color-action)] hover:underline" to="/admin?section=sync">Salud de sincronización</Link>.
      </p>
    </div>
  )
}
