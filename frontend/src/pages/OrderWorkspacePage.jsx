import { useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ArrowLeft, MapPin, CreditCard, Package, Truck, CheckCircle2 } from 'lucide-react'
import api from '../api/client'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Badge } from '../components/ui/badge'
import { formatQ, formatDatetime } from '../lib/utils'

export const orderStateLabel = state => ({
  preparando: 'En preparación',
  enviado_parcial: 'Envío parcial',
  entregado_parcial: 'Entrega parcial',
}[state] || state?.replaceAll('_', ' '))

function apiErrorMessage(error, fallback) {
  const detail = error.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(item => item.msg || 'Dato inválido.').join(' ')
  if (detail && typeof detail.message === 'string') return detail.message
  return fallback
}

const PART_STATE_BADGE = {
  pendiente:         'default',
  confirmado:        'action',
  preparando:        'warning',
  enviado_parcial:   'jade',
  entregado_parcial: 'jade',
  entregado:         'success',
  cancelado:         'error',
  reembolsado:       'default',
}

function Part({ part, orderId, canManage, terminal }) {
  const [amounts, setAmounts] = useState({})
  const [reference, setReference] = useState('')
  const queryClient = useQueryClient()
  const action = useMutation({
    mutationFn: ({ url, body }) => api.post(`/fulfillment/orders/${orderId}/${url}`, body),
    onSuccess: () => {
      toast.success('Avance del pedido actualizado.')
      setAmounts({})
      setReference('')
      for (const key of ['fulfillment', 'order', 'orders', 'vendor-orders', 'vendor-stats', 'admin-orders', 'admin-sales'])
        queryClient.invalidateQueries({ queryKey: [key] })
    },
    onError: e => toast.error(apiErrorMessage(e, 'No se pudo registrar el cambio.')),
  })

  function send() {
    const lineas = part.lineas
      .filter(l => Number(amounts[l.id]) > 0)
      .map(l => ({ pedido_linea_id: l.id, cantidad: Number(amounts[l.id]) }))
    if (!lineas.length) return toast.error('Indica al menos una cantidad para enviar.')
    if (lineas.some(line => !Number.isSafeInteger(line.cantidad))) return toast.error('Las cantidades deben ser números enteros.')
    action.mutate({ url: `parts/${part.id}/shipments`, body: { lineas, referencia: reference || null } })
  }

  const editable = canManage && !terminal && !['cancelado', 'reembolsado'].includes(part.estado)

  return (
    <section className="border border-[var(--color-border)] rounded-[var(--radius-xl)] bg-[var(--color-surface)] shadow-[var(--shadow-sm)] overflow-hidden">
      <header className="flex flex-wrap justify-between gap-3 px-5 py-4 bg-[var(--color-background)] border-b border-[var(--color-border)]">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-full bg-[var(--color-action)]/10 flex items-center justify-center flex-shrink-0">
            <Package size={16} className="text-[var(--color-action)]" />
          </div>
          <div>
            <h2 className="font-semibold font-display text-[var(--color-text-primary)]">{part.vendedor_nombre}</h2>
            <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
              Subpedido #{part.id} · {formatQ(part.subtotal)}
            </p>
          </div>
        </div>
        <Badge variant={PART_STATE_BADGE[part.estado] || 'default'}>{orderStateLabel(part.estado)}</Badge>
      </header>

      <div className="p-5 space-y-5">
        {editable && part.estado === 'confirmado' && (
          <Button loading={action.isPending} onClick={() => action.mutate({ url: `parts/${part.id}/prepare` })} className="gap-2">
            <Package size={14} /> Comenzar preparación
          </Button>
        )}

        <div className="overflow-x-auto rounded-xl border border-[var(--color-border)]">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[var(--color-background)] border-b border-[var(--color-border)]">
                {[
                  'Producto / variante',
                  'Precio',
                  'Pedido',
                  'Enviado',
                  'Entregado',
                  'Por enviar',
                  ...(editable ? ['Enviar ahora'] : []),
                ].map(h => (
                  <th key={h} className="px-3 py-2.5 text-left text-xs font-medium text-[var(--color-text-secondary)] uppercase tracking-wide whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {part.lineas.map(l => (
                <tr key={l.id} className="hover:bg-[var(--color-background)] transition-colors">
                  <td className="px-3 py-3">
                    <p className="font-medium text-[var(--color-text-primary)]">{l.producto_nombre}</p>
                    <p className="text-xs font-mono text-[var(--color-text-muted)]">{l.sku}</p>
                  </td>
                  <td className="px-3 py-3 font-mono whitespace-nowrap text-[var(--color-text-secondary)]">{formatQ(l.precio)}</td>
                  <td className="px-3 py-3 text-[var(--color-text-secondary)]">{l.cantidad}</td>
                  <td className="px-3 py-3 text-[var(--color-text-secondary)]">{l.enviado}</td>
                  <td className="px-3 py-3 text-[var(--color-text-secondary)]">{l.entregado}</td>
                  <td className="px-3 py-3">
                    <span className={l.pendiente_envio > 0 ? 'font-semibold text-[var(--color-action)]' : 'text-[var(--color-text-muted)]'}>
                      {l.pendiente_envio}
                    </span>
                  </td>
                  {editable && (
                    <td className="px-3 py-2.5">
                      <Input
                        aria-label={`Enviar ${l.producto_nombre}`}
                        className="w-24"
                        type="number"
                        inputMode="numeric"
                        min="0"
                        max={l.pendiente_envio}
                        step="1"
                        disabled={!l.pendiente_envio || part.estado === 'pendiente'}
                        value={amounts[l.id] ?? ''}
                        placeholder="0"
                        onKeyDown={e => { if (['.', 'e', 'E', '+', '-', ','].includes(e.key)) e.preventDefault() }}
                        onChange={e => {
                          const value = e.target.value
                          if (value === '' || /^\d+$/.test(value)) setAmounts({ ...amounts, [l.id]: value })
                        }}
                      />
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {editable && part.lineas.some(l => l.pendiente_envio > 0) && part.estado !== 'pendiente' && (
          <div className="flex flex-wrap gap-3 items-center p-4 bg-[var(--color-background)] rounded-xl border border-[var(--color-border)]">
            <Truck size={15} className="text-[var(--color-text-muted)] flex-shrink-0" />
            <Input
              className="max-w-sm flex-1"
              aria-label="Referencia de envío"
              placeholder="Guía o referencia de envío (opcional)"
              maxLength={120}
              value={reference}
              onChange={e => setReference(e.target.value)}
            />
            <Button loading={action.isPending} onClick={send}>Registrar envío</Button>
          </div>
        )}

        <div className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
            Historial de envíos
          </h3>
          {!part.envios.length ? (
            <div className="text-center py-8 border border-dashed border-[var(--color-border)] rounded-xl">
              <Truck size={28} className="mx-auto mb-2 text-[var(--color-border-strong)]" strokeWidth={1.5} />
              <p className="text-sm text-[var(--color-text-muted)]">Todavía no hay envíos registrados.</p>
            </div>
          ) : (
            part.envios.map(s => (
              <article key={s.id} className="border border-[var(--color-border)] rounded-xl overflow-hidden bg-[var(--color-background)]">
                <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-[var(--color-border)]">
                  <div className="flex items-center gap-2">
                    <Truck size={14} className="text-[var(--color-text-muted)]" />
                    <strong className="text-sm font-display">Envío #{s.id}</strong>
                    {s.referencia && (
                      <span className="text-xs font-mono text-[var(--color-text-muted)] bg-[var(--color-border)] px-1.5 py-0.5 rounded">
                        {s.referencia}
                      </span>
                    )}
                  </div>
                  <Badge variant={PART_STATE_BADGE[s.estado] || 'default'}>{orderStateLabel(s.estado)}</Badge>
                </div>
                <div className="px-4 py-3 space-y-2.5">
                  <p className="text-xs text-[var(--color-text-muted)]">
                    {s.fecha_envio ? formatDatetime(s.fecha_envio) : 'Fecha histórica no registrada'}
                  </p>
                  <ul className="space-y-1.5">
                    {s.lineas.map(l => (
                      <li key={l.pedido_linea_id} className="flex items-center gap-2 text-sm">
                        <Package size={12} className="text-[var(--color-text-muted)] flex-shrink-0" />
                        <span className="text-[var(--color-text-primary)]">
                          {part.lineas.find(p => p.id === l.pedido_linea_id)?.producto_nombre}
                          <span className="text-[var(--color-text-muted)]"> — {l.cantidad} unidades</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                  {s.fecha_entrega && (
                    <p className="flex items-center gap-1.5 text-xs text-[var(--color-success)] font-medium">
                      <CheckCircle2 size={12} /> Entregado: {formatDatetime(s.fecha_entrega)}
                    </p>
                  )}
                  {editable && s.estado === 'enviado' && (
                    <Button size="sm" loading={action.isPending} onClick={() => action.mutate({ url: `shipments/${s.id}/deliver` })}>
                      Confirmar entrega
                    </Button>
                  )}
                </div>
              </article>
            ))
          )}
        </div>
      </div>
    </section>
  )
}

export function FulfillmentPanel({ orderId, compact = false }) {
  const cache = useQueryClient()
  const statusAction = useMutation({
    mutationFn: estado => api.patch(`/admin/orders/${orderId}/status`, { estado }),
    onSuccess: () => {
      cache.invalidateQueries({ queryKey: ['fulfillment'] })
      cache.invalidateQueries({ queryKey: ['order'] })
      cache.invalidateQueries({ queryKey: ['admin-orders'] })
      toast.success('Pedido actualizado.')
    },
    onError: e => toast.error(apiErrorMessage(e, 'No se pudo actualizar.')),
  })
  const { data, isLoading, isError } = useQuery({
    queryKey: ['fulfillment', String(orderId)],
    refetchInterval: 15000,
    queryFn: () => api.get(`/fulfillment/orders/${orderId}`).then(r => r.data),
  })

  if (isLoading) return <p className="text-[var(--color-text-secondary)]">Cargando avance de entrega…</p>
  if (isError) return <p role="alert" className="text-[var(--color-error)]">No se pudo cargar el pedido o no tienes acceso.</p>

  const hasActions = data.puede_confirmar || data.puede_cancelar || data.puede_reembolsar

  return (
    <div className="space-y-5">
      {!compact && (
        <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-xl)] overflow-hidden shadow-[var(--shadow-sm)]">
          <div className="h-1" style={{ background: 'linear-gradient(90deg, var(--color-action), var(--color-jade))' }} />
          <div className="px-6 py-5 flex items-start justify-between flex-wrap gap-4">
            <div>
              <p className="text-xs font-sans font-semibold uppercase tracking-widest text-[var(--color-text-muted)] mb-1">
                {data.vista_vendedor ? 'Subpedido' : 'Pedido'}
              </p>
              <h1 className="text-2xl font-bold font-display text-[var(--color-text-primary)]">#{data.id}</h1>
              <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                {data.comprador.nombre} · {formatDatetime(data.fecha)}
              </p>
              <p className="text-base font-semibold font-display mt-2 text-[var(--color-text-primary)]">
                {data.vista_vendedor ? 'Subtotal de tus productos' : 'Total de la compra'}:{' '}
                <span className="text-[var(--color-action)]">{formatQ(data.total)}</span>
              </p>
            </div>
            <Badge variant={PART_STATE_BADGE[data.estado] || 'default'} className="text-sm px-3 py-1.5 flex-shrink-0">
              {orderStateLabel(data.estado)}
            </Badge>
          </div>
        </div>
      )}

      {(data.direccion || !data.vista_vendedor) && (
        <div className="grid gap-4 sm:grid-cols-2">
          {data.direccion && (
            <section className="border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5 bg-[var(--color-surface)] space-y-3 shadow-[var(--shadow-sm)]">
              <h2 className="font-display font-semibold text-sm flex items-center gap-2.5 text-[var(--color-text-primary)]">
                <div className="h-7 w-7 rounded-full bg-[var(--color-action)]/10 flex items-center justify-center flex-shrink-0">
                  <MapPin size={13} className="text-[var(--color-action)]" />
                </div>
                Dirección de entrega
              </h2>
              <div className="pl-9 space-y-0.5">
                <p className="text-sm font-medium text-[var(--color-text-primary)]">{data.direccion.receptor_nombre}</p>
                <p className="text-xs text-[var(--color-text-muted)]">{data.direccion.receptor_telefono}</p>
                <p className="text-sm text-[var(--color-text-secondary)] pt-1">
                  {[data.direccion.linea1, data.direccion.linea2, data.direccion.municipio, data.direccion.departamento]
                    .filter(Boolean).join(', ')}
                </p>
              </div>
            </section>
          )}

          {!data.vista_vendedor && (
            <section className="border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5 bg-[var(--color-surface)] space-y-3 shadow-[var(--shadow-sm)]">
              <h2 className="font-display font-semibold text-sm flex items-center gap-2.5 text-[var(--color-text-primary)]">
                <div className="h-7 w-7 rounded-full bg-[var(--color-action)]/10 flex items-center justify-center flex-shrink-0">
                  <CreditCard size={13} className="text-[var(--color-action)]" />
                </div>
                Resumen comercial
              </h2>
              <div className="pl-9 space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-[var(--color-text-secondary)]">Subtotal</span>
                  <span className="font-mono font-medium">{formatQ(data.subtotal)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-[var(--color-text-secondary)]">IVA (12%)</span>
                  <span className="font-mono font-medium">{formatQ(data.impuestos)}</span>
                </div>
                <div className="flex justify-between text-sm border-t border-[var(--color-border)] pt-2">
                  <span className="font-semibold text-[var(--color-text-primary)]">Total</span>
                  <span className="font-mono font-bold text-[var(--color-text-primary)]">{formatQ(data.total)}</span>
                </div>
                {data.pagos.map((p, i) => (
                  <p key={i} className="text-xs text-[var(--color-text-muted)] pt-0.5">
                    Pago {p.estado}: <span className="font-mono">{formatQ(p.monto)}</span>
                    {p.referencia && <span className="ml-1">· Ref: {p.referencia}</span>}
                  </p>
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {hasActions && (
        <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] px-5 py-4 flex flex-wrap gap-3 items-center shadow-[var(--shadow-sm)]">
          <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] flex-1 min-w-max">
            Acciones del pedido
          </span>
          {data.puede_confirmar && (
            <Button loading={statusAction.isPending} onClick={() => statusAction.mutate('confirmado')}>
              Confirmar pedido
            </Button>
          )}
          {data.puede_cancelar && (
            <Button
              variant="destructive"
              loading={statusAction.isPending}
              onClick={() => {
                if (window.confirm('¿Cancelar antes del envío y reponer las existencias? El reembolso simulado se registra por separado.'))
                  statusAction.mutate('cancelado')
              }}
            >
              Cancelar pedido sin envíos
            </Button>
          )}
          {data.puede_reembolsar && (
            <Button variant="secondary" loading={statusAction.isPending} onClick={() => statusAction.mutate('reembolsado')}>
              Registrar reembolso simulado
            </Button>
          )}
        </div>
      )}

      <p className="text-xs text-center text-[var(--color-text-muted)]">
        El pedido se completa cuando se entregan todas las unidades de todos los vendedores.
      </p>

      {data.subpedidos.map(part => (
        <Part
          key={part.id}
          part={part}
          orderId={orderId}
          canManage={data.puede_gestionar}
          terminal={['cancelado', 'reembolsado'].includes(data.estado)}
        />
      ))}
    </div>
  )
}

export default function OrderWorkspacePage() {
  const { id } = useParams()
  const { pathname } = useLocation()
  const back = pathname.startsWith('/admin')
    ? `/admin?section=${pathname.includes('/sales/') ? 'sales' : 'orders'}`
    : '/vendor'
  return (
    <main className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" className="-ml-2" asChild>
          <Link to={back}>
            <ArrowLeft size={14} /> Volver al listado
          </Link>
        </Button>
        {pathname.includes('/sales/') && (
          <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
            Detalle de venta
          </span>
        )}
      </div>
      <FulfillmentPanel orderId={id} />
    </main>
  )
}
