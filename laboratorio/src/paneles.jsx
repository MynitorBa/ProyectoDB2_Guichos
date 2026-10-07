import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CreditCard, FlaskConical, PlayCircle, ShieldCheck, ScrollText, Network, Container,
  CheckCircle2, XCircle, MinusCircle, PauseCircle, RotateCw, Copy, Database, Search, BarChart2,
  GitBranch, Zap,
} from 'lucide-react'
import { toast } from 'sonner'

import { api } from './api'
import { Boton, Cargando, Etiqueta, Panel, cn, duracion, horaLocal } from './ui'

const mensajeDe = (err, porDefecto) => err?.message || porDefecto

// ── Pasarela de pagos ─────────────────────────────────────────────────────────

const MODOS_PASARELA = [
  { modo: 'aprobar', label: 'Aprobar', detalle: 'Cobra y responde aprobado.' },
  { modo: 'rechazar', label: 'Rechazar', detalle: 'Fondos insuficientes: la saga compensa el pedido.' },
  { modo: 'timeout', label: 'Timeout', detalle: 'Cobra pero no responde a tiempo: pago en verificación.' },
  { modo: 'cobrar_y_fallar', label: 'Cobrar y fallar', detalle: 'Cobra y responde 500: el reintento idempotente lo resuelve.' },
  { modo: 'error_antes', label: 'Error 503', detalle: 'No cobra ni responde: verificación y luego compensación.' },
]

export function PanelPasarela({ estado }) {
  const queryClient = useQueryClient()
  const cambiar = useMutation({
    mutationFn: api.modoPasarela,
    onSuccess: (_, modo) => { toast.success(`Pasarela en modo «${modo}».`); queryClient.invalidateQueries({ queryKey: ['fallas'] }) },
    onError: (err) => toast.error(mensajeDe(err, 'No se pudo cambiar el modo.')),
  })
  const actual = estado?.pasarela?.modo
  return (
    <Panel icono={CreditCard} titulo="Pasarela de pagos simulada"
      descripcion="Sistema externo, independiente de MySQL (:8001). Su comportamiento decide el desenlace de cada compra.">
      {!estado ? <Cargando className="h-48" /> : !estado.pasarela ? (
        <p className="text-sm text-[var(--color-error)]">La pasarela no responde en :8001. Inicia el sistema con <code>start-dev.ps1</code>.</p>
      ) : (
        <div className="space-y-1.5">
          {MODOS_PASARELA.map((m) => (
            <button key={m.modo} type="button" onClick={() => cambiar.mutate(m.modo)} disabled={cambiar.isPending}
              aria-pressed={actual === m.modo}
              className={cn('w-full flex items-center gap-3 text-left px-3 py-2 rounded-lg border transition-colors',
                actual === m.modo ? 'border-[var(--color-action)] bg-[var(--color-action)]/5' : 'border-[var(--color-border)] hover:border-[var(--color-action)]/40')}>
              <span className="flex-1">
                <span className="block text-sm font-semibold">{m.label}</span>
                <span className="block text-xs text-[var(--color-text-muted)]">{m.detalle}</span>
              </span>
              {actual === m.modo && <Etiqueta tono="action">Activo</Etiqueta>}
            </button>
          ))}
        </div>
      )}
    </Panel>
  )
}

// ── Puntos de falla ───────────────────────────────────────────────────────────

export function PanelPuntosFalla({ estado }) {
  const queryClient = useQueryClient()
  const refrescar = () => queryClient.invalidateQueries({ queryKey: ['fallas'] })
  const cambiar = useMutation({
    mutationFn: ({ punto, modo }) => api.activarFalla(punto, modo),
    onSuccess: refrescar,
    onError: (err) => toast.error(mensajeDe(err, 'No se pudo configurar el punto de falla.')),
  })
  const limpiar = useMutation({ mutationFn: api.desactivarFallas, onSuccess: refrescar })
  return (
    <Panel icono={FlaskConical} titulo="Puntos de falla"
      descripcion="Simulan que el proceso del backend cae en un punto exacto del flujo. «Una vez» se desactiva tras dispararse."
      acciones={<Boton variante="secondary" onClick={() => limpiar.mutate()}>Desactivar todos</Boton>}>
      {!estado ? <Cargando className="h-48" /> : (
        <ul className="space-y-1.5">
          {estado.puntos.map((p) => (
            <li key={p.punto} className="flex items-center gap-3 rounded-lg border border-[var(--color-border)] px-3 py-2">
              <div className="flex-1 min-w-0">
                <p className="font-mono text-xs">{p.punto}</p>
                <p className="text-xs text-[var(--color-text-muted)]">{p.descripcion}{p.disparos > 0 && ` · disparada ${p.disparos}×`}</p>
              </div>
              <div className="flex rounded-md border border-[var(--color-border)] overflow-hidden shrink-0" role="group" aria-label={`Modo de ${p.punto}`}>
                {[['off', 'Off'], ['una_vez', 'Una vez'], ['siempre', 'Siempre']].map(([modo, label]) => {
                  const activo = (p.modo || 'off') === modo
                  return (
                    <button key={modo} type="button" aria-pressed={activo}
                      onClick={() => cambiar.mutate({ punto: p.punto, modo })}
                      className={cn('px-2 py-1 text-[11px]', activo
                        ? (modo === 'off' ? 'bg-[var(--color-border)] font-semibold' : 'bg-[var(--color-error)] text-white font-semibold')
                        : 'hover:bg-[var(--color-border)]/60')}>
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
  )
}

// ── Componentes de la arquitectura ────────────────────────────────────────────

const CONTENEDORES = [
  { nombre: 'MongoDB', contenedor: 'tiendaya_mongo', efecto: 'Catálogo y su proyección; el índice de búsqueda también espera.' },
  { nombre: 'Elasticsearch', contenedor: 'tiendaya_elasticsearch', efecto: 'La búsqueda pasa a modo degradado sobre MongoDB.' },
  { nombre: 'Neo4j', contenedor: 'tiendaya_neo4j', efecto: 'Las compras esperan para habilitar reseñas verificadas.' },
  { nombre: 'Cassandra', contenedor: 'tiendaya_cassandra', efecto: 'La analítica de ventas se atrasa.' },
  { nombre: 'Redis', contenedor: 'tiendaya_redis', efecto: 'El checkout responde 503: el carrito no está disponible.', pausa: true },
]

function Comando({ texto }) {
  return (
    <button type="button" title="Copiar"
      onClick={() => navigator.clipboard?.writeText(texto).then(() => toast.success('Comando copiado'))}
      className="group flex items-center gap-1.5 rounded bg-[var(--color-lab)] text-gray-100 px-2 py-1 font-mono text-[11px] hover:bg-black">
      {texto}<Copy size={11} className="opacity-50 group-hover:opacity-100" />
    </button>
  )
}

export function PanelComponentes() {
  return (
    <Panel icono={Container} titulo="Tumbar componentes"
      descripcion="Para simular la caída de una base de datos, ejecuta estos comandos en una terminal. El laboratorio no ejecuta nada en tu máquina; observa el efecto en «Outbox en vivo».">
      <ul className="space-y-2">
        {CONTENEDORES.map((c) => (
          <li key={c.contenedor} className="rounded-lg border border-[var(--color-border)] px-3 py-2 space-y-1.5">
            <p className="text-sm"><span className="font-semibold">{c.nombre}</span> <span className="text-xs text-[var(--color-text-muted)]">· {c.efecto}</span></p>
            <div className="flex flex-wrap gap-1.5">
              <Comando texto={`docker ${c.pausa ? 'pause' : 'stop'} ${c.contenedor}`} />
              <Comando texto={`docker ${c.pausa ? 'unpause' : 'start'} ${c.contenedor}`} />
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  )
}

// ── Outbox en vivo ────────────────────────────────────────────────────────────

const DESTINOS = {
  mongo: { label: 'MongoDB', Icono: Database },
  busqueda: { label: 'Elasticsearch', Icono: Search },
  cassandra: { label: 'Cassandra', Icono: BarChart2 },
  neo4j: { label: 'Neo4j', Icono: GitBranch },
  redis: { label: 'Redis', Icono: Zap },
}

function estadoDestino(d) {
  if (d.fallido > 0) return ['Fallidos', 'error']
  if (d.error > 0 || d.en_pausa) return ['Reintentando', 'warning']
  if (d.pendiente + d.procesando > 0) return ['Sincronizando', 'action']
  return ['Al día', 'success']
}

export function PanelOutbox() {
  const queryClient = useQueryClient()
  const outbox = useQuery({ queryKey: ['outbox'], queryFn: api.outbox, refetchInterval: 2000 })
  const reintentar = useMutation({
    mutationFn: api.reintentarEventos,
    onSuccess: (r) => { toast.success(`${r.reintentados} evento(s) devueltos a la cola.`); queryClient.invalidateQueries({ queryKey: ['outbox'] }) },
  })
  const destinos = outbox.data?.destinos || []
  const problemas = outbox.data?.problemas || []
  return (
    <Panel icono={Network} titulo="Outbox en vivo"
      descripcion="Eventos pendientes de proyectar desde MySQL hacia cada componente (cada 2 s). Con un componente caído, sus eventos quedan retenidos con backoff y los demás siguen al día."
      acciones={problemas.length > 0 && <Boton variante="secondary" onClick={() => reintentar.mutate({})}><RotateCw size={13} /> Reintentar ya</Boton>}>
      {outbox.isLoading ? <Cargando className="h-28" /> : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
            {destinos.map((d) => {
              const { label, Icono } = DESTINOS[d.destino]
              const [texto, tono] = estadoDestino(d)
              return (
                <div key={d.destino} className="rounded-lg border border-[var(--color-border)] p-2.5 space-y-1.5">
                  <p className="flex items-center gap-1.5 text-xs font-semibold"><Icono size={13} />{label}
                    {d.en_pausa && <PauseCircle size={12} className="text-[var(--color-warning)]" aria-label="En pausa" />}</p>
                  <Etiqueta tono={tono}>{texto}</Etiqueta>
                  <p className="text-[11px] text-[var(--color-text-muted)] font-mono">
                    pend {d.pendiente + d.procesando} · err {d.error} · fall {d.fallido}
                  </p>
                  <p className="text-[11px] text-[var(--color-text-muted)]">más antiguo: {duracion(d.pendiente_mas_antiguo_segundos)}</p>
                </div>
              )
            })}
          </div>
          {problemas.length > 0 && (
            <ul className="mt-3 space-y-1 max-h-40 overflow-y-auto">
              {problemas.slice(0, 10).map((e) => (
                <li key={e.id} className="text-[11px] font-mono text-[var(--color-text-secondary)] truncate" title={e.ultimo_error}>
                  <Etiqueta tono={e.estado === 'fallido' ? 'error' : 'warning'} className="mr-1.5">{e.estado}</Etiqueta>
                  {e.destino} · {e.tipo_evento} · {e.agregado} · intento {e.intentos} · próximo {horaLocal(e.siguiente_intento_en)}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Panel>
  )
}

// ── Recuperación ──────────────────────────────────────────────────────────────

export function PanelRecuperacion() {
  const queryClient = useQueryClient()
  const [ultima, setUltima] = useState(null)
  const recuperar = useMutation({
    mutationFn: api.recuperar,
    onSuccess: (r) => {
      setUltima({ ...r, en: new Date().toISOString() })
      queryClient.invalidateQueries({ queryKey: ['bitacora'] })
      queryClient.invalidateQueries({ queryKey: ['consistencia'] })
    },
    onError: (err) => toast.error(mensajeDe(err, 'No se pudo ejecutar la recuperación.')),
  })
  return (
    <Panel icono={PlayCircle} titulo="Recuperación del checkout"
      descripcion="El backend la ejecuta solo cada 5 s: el reconciliador resuelve pagos en verificación consultando la pasarela y el recolector atiende pedidos cuya reserva venció a mitad de la saga."
      acciones={<Boton cargando={recuperar.isPending} onClick={() => recuperar.mutate()}>Ejecutar ahora</Boton>}>
      {ultima ? (
        <div className="text-sm space-y-0.5">
          <p className="text-xs text-[var(--color-text-muted)]">{horaLocal(ultima.en)}</p>
          {['reconciliador', 'recolector'].map((tarea) => {
            const entradas = Object.entries(ultima[tarea] || {})
            return <p key={tarea}><span className="font-semibold capitalize">{tarea}: </span>
              {entradas.length ? entradas.map(([k, v]) => `${v} ${k.replace('_', ' ')}`).join(', ') : 'nada pendiente'}</p>
          })}
        </div>
      ) : <p className="text-sm text-[var(--color-text-muted)]">Ejecútala para ver qué resolvió en este momento.</p>}
    </Panel>
  )
}

// ── Invariantes ───────────────────────────────────────────────────────────────

export function PanelInvariantes() {
  const consulta = useQuery({ queryKey: ['consistencia'], queryFn: api.consistencia, refetchInterval: 15000 })
  const datos = consulta.data
  return (
    <Panel icono={ShieldCheck} titulo="Invariantes de consistencia"
      descripcion="Propiedades que deben cumplirse siempre, incluso después de una falla; se verifican contra MySQL, la pasarela, MongoDB y Elasticsearch."
      acciones={<Boton variante="secondary" cargando={consulta.isFetching} onClick={() => consulta.refetch()}>Verificar ahora</Boton>}>
      {!datos ? <Cargando className="h-40" /> : (
        <>
          <p className={cn('text-sm font-semibold mb-2', datos.ok ? 'text-[var(--color-success)]' : 'text-[var(--color-error)]')}>
            {datos.ok ? 'Todos los invariantes se cumplen.' : 'Hay invariantes violados.'}
            <span className="font-normal text-xs text-[var(--color-text-muted)] ml-2">{horaLocal(datos.generado_en)}</span>
          </p>
          <ul className="divide-y divide-[var(--color-border)]">
            {datos.invariantes.map((inv) => (
              <li key={inv.id} className="py-2 flex gap-2.5">
                {inv.ok === true && <CheckCircle2 size={16} className="text-[var(--color-success)] shrink-0 mt-0.5" />}
                {inv.ok === false && <XCircle size={16} className="text-[var(--color-error)] shrink-0 mt-0.5" />}
                {inv.ok === null && <MinusCircle size={16} className="text-[var(--color-text-muted)] shrink-0 mt-0.5" />}
                <div className="min-w-0">
                  <p className="text-sm"><span className="font-mono text-xs text-[var(--color-text-muted)] mr-1.5">{inv.id}</span>{inv.titulo}</p>
                  <p className="text-xs text-[var(--color-text-muted)]">{inv.detalle}</p>
                  {inv.nota && <p className="text-xs text-[var(--color-warning)]">Nota: {inv.nota}</p>}
                  {inv.ejemplos?.length > 0 && (
                    <pre className="mt-1 text-[11px] font-mono bg-[var(--color-background)] rounded p-2 overflow-x-auto">{inv.ejemplos.map((e) => JSON.stringify(e)).join('\n')}</pre>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </Panel>
  )
}

// ── Bitácora de la saga ───────────────────────────────────────────────────────

const TONO_RESULTADO = {
  ok: 'success', aprobado: 'success', rechazado: 'error', no_encontrado: 'warning',
  desconocido: 'warning', no_enviado: 'warning', pendiente: 'warning', reembolsado: 'default',
}

export function PanelBitacora() {
  const consulta = useQuery({ queryKey: ['bitacora'], queryFn: () => api.bitacora(80), refetchInterval: 2000 })
  const pasos = consulta.data || []
  return (
    <Panel icono={ScrollText} titulo="Bitácora de la saga del checkout"
      descripcion="Cada transición de cada compra: reserva → cobro → confirmación o compensación, incluidas las del reconciliador y el recolector (cada 2 s).">
      {pasos.length === 0 ? <p className="text-sm text-[var(--color-text-muted)]">Aún no hay compras registradas con la saga.</p> : (
        <div className="overflow-x-auto max-h-[30rem] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-[var(--color-surface)]">
              <tr className="text-left text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)]">
                <th className="py-2 pr-3">Hora</th><th className="py-2 pr-3">Pedido</th><th className="py-2 pr-3">Paso</th>
                <th className="py-2 pr-3">Resultado</th><th className="py-2 pr-3">Pedido ahora</th><th className="py-2">Pago ahora</th>
              </tr>
            </thead>
            <tbody>
              {pasos.map((p) => (
                <tr key={p.id} className="border-b border-[var(--color-border)] last:border-0">
                  <td className="py-1.5 pr-3 text-xs font-mono whitespace-nowrap">{horaLocal(p.creado_en)}</td>
                  <td className="py-1.5 pr-3 font-mono">#{p.pedido_id}</td>
                  <td className="py-1.5 pr-3">{p.paso}</td>
                  <td className="py-1.5 pr-3"><Etiqueta tono={TONO_RESULTADO[p.resultado] || 'default'}>{p.resultado}</Etiqueta></td>
                  <td className="py-1.5 pr-3 text-xs">{p.pedido_estado}{p.motivo_cancelacion && <span className="text-[var(--color-text-muted)]"> · {p.motivo_cancelacion}</span>}</td>
                  <td className="py-1.5 text-xs">{p.pago_estado}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}
