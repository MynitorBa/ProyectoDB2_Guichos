import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { Package, Bell, ChevronDown, ChevronRight, Store } from 'lucide-react'
import { toast } from 'sonner'
import { getVendorStats, getVendorOrders, updateVendorOrderStatus, getVendorEstados } from '../api/vendor'
import { getNotifications, markAllAsRead } from '../api/notifications'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../components/ui/select'
import { Skeleton } from '../components/ui/skeleton'
import { formatQ, formatDate, cn } from '../lib/utils'

const ESTADO_BADGE = {
  pendiente: 'warning', confirmado: 'action', en_preparacion: 'action',
  enviado: 'jade', entregado: 'success', cancelado: 'error', reembolsado: 'default',
}
const ESTADO_LABEL = {
  pendiente: 'Pendiente', confirmado: 'Confirmado', en_preparacion: 'En preparación',
  enviado: 'Enviado', entregado: 'Entregado', cancelado: 'Cancelado', reembolsado: 'Reembolsado',
}

function StatCard({ label, value, sub }) {
  return (
    <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5">
      <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-1">{label}</p>
      <p className="font-mono font-bold text-3xl text-[var(--color-text-primary)]">{value}</p>
      {sub && <p className="font-sans text-xs text-[var(--color-text-muted)] mt-1">{sub}</p>}
    </div>
  )
}

export default function VendorPage() {
  const [tab, setTab] = useState('orders')
  const [page, setPage] = useState(1)
  const [expandedId, setExpandedId] = useState(null)
  const [updatingId, setUpdatingId] = useState(null)
  const queryClient = useQueryClient()
  const PAGE_SIZE = 15

  const { data: stats, isLoading: statsLoading, error: statsError } = useQuery({
    queryKey: ['vendor-stats'],
    queryFn: () => getVendorStats().then(r => r.data),
    retry: false,
  })

  const { data: ordersData, isLoading: ordersLoading } = useQuery({
    queryKey: ['vendor-orders', page],
    queryFn: () => getVendorOrders(page, PAGE_SIZE).then(r => r.data),
    placeholderData: keepPreviousData,
    enabled: statsError?.response?.status !== 403,
    retry: false,
  })

  const { data: notifs, isLoading: notifsLoading } = useQuery({
    queryKey: ['vendor-notifications'],
    queryFn: () => getNotifications().then(r => r.data),
    enabled: tab === 'notificaciones',
  })

  const { data: estadosDisponibles = [] } = useQuery({
    queryKey: ['vendor-estados'],
    queryFn: () => getVendorEstados().then(r => r.data),
    staleTime: Infinity,
  })

  const statusMutation = useMutation({
    mutationFn: ({ pedidoId, estado }) => updateVendorOrderStatus(pedidoId, estado),
    onSuccess: (_, { pedidoId, estado }) => {
      toast.success(`Pedido #${pedidoId} actualizado a "${ESTADO_LABEL[estado] || estado}".`)
      queryClient.invalidateQueries({ queryKey: ['vendor-orders'] })
      queryClient.invalidateQueries({ queryKey: ['vendor-stats'] })
      setUpdatingId(null)
    },
    onError: (err) => {
      toast.error(err?.response?.data?.detail || 'No se pudo cambiar el estado.')
      setUpdatingId(null)
    },
  })

  async function handleMarkAllRead() {
    await markAllAsRead()
    queryClient.invalidateQueries({ queryKey: ['vendor-notifications'] })
    queryClient.invalidateQueries({ queryKey: ['notif-count'] })
    toast.success('Notificaciones marcadas como leídas.')
  }

  function handleStatusChange(pedidoId, estado) {
    setUpdatingId(pedidoId)
    statusMutation.mutate({ pedidoId, estado })
  }

  const pedidos = ordersData?.items || []
  const totalPages = ordersData?.total_pages || 1
  const unreadCount = (notifs || []).filter(n => !n.leida).length

  const profileNotConfigured = statsError?.response?.status === 403

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <div className="max-w-[1200px] mx-auto px-4 py-8 space-y-6">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-full bg-[var(--color-jade)]/10 flex items-center justify-center">
            <Store size={20} className="text-[var(--color-jade)]" />
          </div>
          <div>
            <h1 className="font-display font-bold text-2xl text-[var(--color-text-primary)]">Panel de Vendedor</h1>
            {stats?.nombre_comercial && (
              <p className="font-sans text-sm text-[var(--color-text-muted)]">{stats.nombre_comercial}</p>
            )}
          </div>
        </div>

        {profileNotConfigured && (
          <div className="border border-[var(--color-warning,#f59e0b)]/40 bg-[var(--color-warning,#f59e0b)]/10 rounded-[var(--radius-lg)] px-5 py-4">
            <p className="font-display font-semibold text-sm text-[var(--color-text-primary)] mb-1">Perfil de vendedor no configurado</p>
            <p className="font-sans text-xs text-[var(--color-text-secondary)]">
              Tu cuenta tiene el rol de vendedor, pero aún no tiene un perfil comercial asignado.
              Pide al administrador que vaya a <strong>Panel Admin → Usuarios</strong> y haga clic en
              <strong> "Perfil vendedor"</strong> en tu fila para ingresar el nombre de tu negocio y NIT.
            </p>
          </div>
        )}

        {!profileNotConfigured && <>
        {/* Stat cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {statsLoading
            ? Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-24 w-full" />)
            : <>
                <StatCard label="Pedidos con mis productos" value={stats?.total_pedidos ?? '—'} />
                <StatCard label="Mis ingresos totales" value={stats ? formatQ(stats.ingresos_totales) : '—'} sub="Sin cancelados/reembolsados" />
                <StatCard label="Pedidos pendientes" value={stats?.pendientes ?? '—'} />
              </>
          }
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-[var(--color-border)]">
          <button
            onClick={() => setTab('orders')}
            className={cn('px-4 py-2.5 font-display font-semibold text-sm transition-colors border-b-2 -mb-px', tab === 'orders' ? 'border-[var(--color-action)] text-[var(--color-action)]' : 'border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]')}
          >
            <Package size={14} className="inline mr-1.5" />Mis pedidos
          </button>
          <button
            onClick={() => setTab('notificaciones')}
            className={cn('px-4 py-2.5 font-display font-semibold text-sm transition-colors border-b-2 -mb-px relative', tab === 'notificaciones' ? 'border-[var(--color-action)] text-[var(--color-action)]' : 'border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]')}
          >
            <Bell size={14} className="inline mr-1.5" />Notificaciones
            {unreadCount > 0 && (
              <span className="ml-1.5 h-4 min-w-[16px] px-1 inline-flex items-center justify-center rounded-full bg-[var(--color-action)] text-white text-[10px] font-bold">{unreadCount}</span>
            )}
          </button>
        </div>

        {/* Orders tab */}
        {tab === 'orders' && (
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-[var(--color-background)]">
                    {['', 'Pedido #', 'Fecha', 'Comprador', 'Mi subtotal', 'Estado', 'Cambiar estado'].map((h, i) => (
                      <th key={i} className="px-4 py-3 text-left font-sans font-semibold text-xs uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)] whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ordersLoading
                    ? Array.from({ length: 5 }).map((_, i) => (
                        <tr key={i}><td colSpan={7} className="px-4 py-2"><Skeleton className="h-8 w-full" /></td></tr>
                      ))
                    : pedidos.length === 0
                      ? <tr><td colSpan={7} className="px-4 py-10 text-center font-sans text-sm text-[var(--color-text-muted)]">Aún no tienes pedidos con tus productos.</td></tr>
                      : pedidos.map((pedido, idx) => {
                          const isExpanded = expandedId === pedido.id
                          const isUpdating = updatingId === pedido.id
                          return (
                            <React.Fragment key={pedido.id}>
                              <tr className={cn('border-b border-[var(--color-border)]', idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]')}>
                                <td className="px-4 py-3">
                                  <button onClick={() => setExpandedId(isExpanded ? null : pedido.id)} className="text-[var(--color-text-muted)]">
                                    {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                  </button>
                                </td>
                                <td className="px-4 py-3 font-mono font-semibold text-[var(--color-text-primary)]">#{pedido.id}</td>
                                <td className="px-4 py-3 font-sans text-xs text-[var(--color-text-secondary)] whitespace-nowrap">{formatDate(pedido.fecha)}</td>
                                <td className="px-4 py-3">
                                  <p className="font-display font-semibold text-xs text-[var(--color-text-primary)]">{pedido.comprador?.nombre}</p>
                                  <p className="font-sans text-[10px] text-[var(--color-text-muted)]">{pedido.comprador?.email}</p>
                                </td>
                                <td className="px-4 py-3 font-mono font-bold text-[var(--color-action)]">{formatQ(pedido.subtotal_mis_productos)}</td>
                                <td className="px-4 py-3">
                                  <Badge variant={ESTADO_BADGE[pedido.estado] || 'default'}>{ESTADO_LABEL[pedido.estado] || pedido.estado}</Badge>
                                </td>
                                <td className="px-4 py-3 w-40">
                                  <Select
                                    value={pedido.estado}
                                    onValueChange={(v) => handleStatusChange(pedido.id, v)}
                                    disabled={isUpdating || ['cancelado', 'reembolsado'].includes(pedido.estado)}
                                  >
                                    <SelectTrigger className="h-8 text-xs">
                                      <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                      {estadosDisponibles.map(e => (
                                        <SelectItem key={e} value={e}>{ESTADO_LABEL[e] || e}</SelectItem>
                                      ))}
                                    </SelectContent>
                                  </Select>
                                </td>
                              </tr>
                              {isExpanded && pedido.mis_lineas?.length > 0 && (
                                <tr className="bg-[var(--color-background)]">
                                  <td colSpan={7} className="px-8 py-3">
                                    <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-2">Mis productos en este pedido</p>
                                    <table className="w-full text-xs border border-[var(--color-border)] rounded-[var(--radius-md)] overflow-hidden">
                                      <thead>
                                        <tr className="bg-[var(--color-border)]/30">
                                          {['Producto', 'Precio unit.', 'Cantidad', 'Subtotal'].map(h => (
                                            <th key={h} className="px-3 py-2 text-left font-sans font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">{h}</th>
                                          ))}
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {pedido.mis_lineas.map((l, j) => (
                                          <tr key={j} className={j % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]'}>
                                            <td className="px-3 py-2 font-display font-medium text-[var(--color-text-primary)]">{l.producto_nombre}</td>
                                            <td className="px-3 py-2 font-mono">{formatQ(l.precio_unitario)}</td>
                                            <td className="px-3 py-2 font-mono">{l.cantidad}</td>
                                            <td className="px-3 py-2 font-mono font-semibold">{formatQ(l.subtotal_linea)}</td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </td>
                                </tr>
                              )}
                            </React.Fragment>
                          )
                        })
                  }
                </tbody>
              </table>
            </div>
            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-3 p-4 border-t border-[var(--color-border)]">
                <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Anterior</Button>
                <span className="font-sans text-sm text-[var(--color-text-secondary)]">{page} / {totalPages}</span>
                <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Siguiente</Button>
              </div>
            )}
          </div>
        )}

        {/* Notifications tab */}
        {tab === 'notificaciones' && (
          <div className="space-y-3">
            <div className="flex justify-end">
              <Button variant="secondary" size="sm" onClick={handleMarkAllRead}>Marcar todas como leídas</Button>
            </div>
            {notifsLoading
              ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20 w-full" />)
              : (notifs || []).length === 0
                ? (
                    <div className="text-center py-16 text-[var(--color-text-muted)] font-sans text-sm">
                      No tienes notificaciones todavía.
                    </div>
                  )
                : (notifs || []).map(n => (
                    <div
                      key={n.id}
                      className={cn(
                        'bg-[var(--color-surface)] border rounded-[var(--radius-lg)] px-4 py-3 flex items-start gap-3',
                        n.leida ? 'border-[var(--color-border)]' : 'border-[var(--color-action)]/40 bg-[var(--color-action)]/5'
                      )}
                    >
                      {!n.leida && <div className="w-2 h-2 rounded-full bg-[var(--color-action)] mt-1.5 shrink-0" />}
                      <div className={cn('flex-1', n.leida && 'pl-5')}>
                        <p className="font-display font-semibold text-sm text-[var(--color-text-primary)]">{n.titulo}</p>
                        <p className="font-sans text-xs text-[var(--color-text-secondary)] mt-0.5">{n.mensaje}</p>
                        <p className="font-sans text-[10px] text-[var(--color-text-muted)] mt-1">{formatDate(n.fecha)}</p>
                      </div>
                    </div>
                  ))
            }
          </div>
        )}
        </>}
      </div>
    </div>
  )
}
