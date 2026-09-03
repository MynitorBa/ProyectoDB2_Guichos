import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, Package, ClipboardList, Store, TrendingUp } from 'lucide-react'
import { getVendorStats, getVendorOrders } from '../api/vendor'
import { getNotifications, markAllAsRead } from '../api/notifications'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { formatQ, formatDate } from '../lib/utils'
import { CatalogRequestsSection } from '../components/vendor/CatalogRequestsSection'
import { VendorOffers } from '../components/vendor/VendorOffers'
import { orderStateLabel } from './OrderWorkspacePage'

const ESTADO_BADGE = {
  pendiente:         'warning',
  confirmado:        'action',
  preparando:        'action',
  enviado_parcial:   'jade',
  entregado_parcial: 'jade',
  entregado:         'success',
  cancelado:         'error',
  reembolsado:       'default',
}

const NAV_TABS = [
  { key: 'orders',        label: 'Mis pedidos',             icon: ClipboardList },
  { key: 'offers',        label: 'Mis ofertas',             icon: TrendingUp    },
  { key: 'requests',      label: 'Solicitudes de catálogo', icon: Store         },
  { key: 'notifications', label: 'Notificaciones',          icon: Bell          },
]

export default function VendorPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'orders'
  const [page, setPage] = useState(1)
  const cache = useQueryClient()

  const { data: stats, error } = useQuery({
    queryKey: ['vendor-stats'],
    queryFn: () => getVendorStats().then(r => r.data),
    retry: false,
  })
  const { data: orders, isLoading } = useQuery({
    queryKey: ['vendor-orders', page],
    queryFn: () => getVendorOrders(page, 20).then(r => r.data),
    enabled: tab === 'orders',
  })
  const { data: notifs = [] } = useQuery({
    queryKey: ['vendor-notifications'],
    queryFn: () => getNotifications().then(r => r.data),
    enabled: tab === 'notifications',
  })

  if (error) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-8">
        <p role="alert" className="font-sans text-sm text-[var(--color-error)]">
          {error.response?.data?.detail || 'No se pudo cargar el perfil de vendedor.'}
        </p>
      </div>
    )
  }

  return (
    <main className="max-w-6xl mx-auto px-6 py-8 space-y-6">
      {/* ── Encabezado ── */}
      <header className="space-y-1">
        <h1 className="font-display font-bold text-2xl text-[var(--color-text-primary)]">
          Panel de vendedor
        </h1>
        {stats?.nombre_comercial && (
          <p className="font-sans text-sm text-[var(--color-text-muted)]">
            {stats.nombre_comercial}
          </p>
        )}
      </header>

      {/* ── Tarjetas de estadísticas ── */}
      <div className="grid sm:grid-cols-3 gap-4">
        {[
          ['Mis pedidos',     stats?.total_pedidos],
          ['Ingresos totales', stats ? formatQ(stats.ingresos_totales) : '—'],
          ['Por preparar',    stats?.pendientes],
        ].map(([label, value]) => (
          <div
            key={label}
            className="border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5 bg-[var(--color-surface)] shadow-[var(--shadow-sm)]"
          >
            <p className="font-sans text-sm text-[var(--color-text-muted)] mb-1">{label}</p>
            <strong className="font-display font-bold text-2xl text-[var(--color-text-primary)]">
              {value ?? '—'}
            </strong>
          </div>
        ))}
      </div>

      {/* ── Navegación por pestañas ── */}
      <nav className="flex flex-wrap gap-2 border-b border-[var(--color-border)] pb-3">
        {NAV_TABS.map(({ key, label, icon: Icon }) => (
          <Button
            key={key}
            variant={tab === key ? 'primary' : 'secondary'}
            onClick={() => setParams({ tab: key })}
            className="gap-1.5"
          >
            <Icon size={14} />
            {label}
          </Button>
        ))}
      </nav>

      {/* ── Contenido de cada pestaña ── */}
      {tab === 'offers' && <VendorOffers />}
      {tab === 'requests' && <CatalogRequestsSection />}

      {tab === 'orders' && (
        <section className="space-y-4">
          <div>
            <h2 className="font-display font-semibold text-xl text-[var(--color-text-primary)]">
              Mis pedidos
            </h2>
            <p className="font-sans text-sm text-[var(--color-text-secondary)] mt-1">
              Abre un pedido para preparar tus productos, registrar envíos parciales y confirmar sus entregas.
            </p>
          </div>

          <div className="overflow-x-auto border border-[var(--color-border)] rounded-[var(--radius-lg)]">
            <table className="w-full text-sm font-sans">
              <thead>
                <tr className="bg-[var(--color-background)] border-b border-[var(--color-border)]">
                  {['Pedido', 'Fecha', 'Comprador', 'Mis productos', 'Mi subtotal', 'Estado'].map(h => (
                    <th
                      key={h}
                      className="px-3 py-2.5 text-left text-xs font-medium text-[var(--color-text-secondary)] uppercase tracking-wide whitespace-nowrap"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {isLoading ? (
                  <tr>
                    <td colSpan={6} className="px-3 py-6 text-center font-sans text-sm text-[var(--color-text-muted)]">
                      Cargando…
                    </td>
                  </tr>
                ) : orders?.items?.length ? (
                  orders.items.map(p => (
                    <tr
                      key={p.pedido_vendedor_id}
                      role="link"
                      tabIndex={0}
                      onClick={() => navigate('/vendor/orders/' + p.id)}
                      onKeyDown={e => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          navigate('/vendor/orders/' + p.id)
                        }
                      }}
                      className="hover:bg-[var(--color-background)] cursor-pointer transition-colors focus-visible:outline-2 focus-visible:outline-[var(--color-action)]"
                    >
                      <td className="px-3 py-3">
                        <Button variant="link" asChild>
                          <Link to={'/vendor/orders/' + p.id}>
                            Abrir #{p.id}
                          </Link>
                        </Button>
                      </td>
                      <td className="px-3 py-3 text-[var(--color-text-secondary)] whitespace-nowrap">
                        {formatDate(p.fecha)}
                      </td>
                      <td className="px-3 py-3 text-[var(--color-text-primary)]">
                        {p.comprador?.nombre}
                      </td>
                      <td className="px-3 py-3 text-[var(--color-text-secondary)] max-w-[220px]">
                        <span className="line-clamp-2">
                          {p.mis_lineas.map(l => l.producto_nombre + ' × ' + l.cantidad).join(', ')}
                        </span>
                      </td>
                      <td className="px-3 py-3 font-mono font-semibold text-[var(--color-text-primary)] whitespace-nowrap">
                        {formatQ(p.subtotal_mis_productos)}
                      </td>
                      <td className="px-3 py-3">
                        <Badge variant={ESTADO_BADGE[p.estado] || 'default'}>
                          {orderStateLabel(p.estado)}
                        </Badge>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6} className="px-3 py-12 text-center">
                      <Package
                        size={36}
                        className="mx-auto mb-3 text-[var(--color-border-strong)]"
                        strokeWidth={1.5}
                      />
                      <p className="font-sans text-sm text-[var(--color-text-muted)]">
                        No tienes pedidos todavía.
                      </p>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-center gap-3">
            <Button
              variant="secondary"
              size="sm"
              disabled={page === 1}
              onClick={() => setPage(p => p - 1)}
            >
              Anterior
            </Button>
            <span className="font-sans text-sm text-[var(--color-text-secondary)]">
              {page} / {orders?.total_pages || 1}
            </span>
            <Button
              variant="secondary"
              size="sm"
              disabled={page >= (orders?.total_pages || 1)}
              onClick={() => setPage(p => p + 1)}
            >
              Siguiente
            </Button>
          </div>
        </section>
      )}

      {tab === 'notifications' && (
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-display font-semibold text-xl text-[var(--color-text-primary)]">
              Notificaciones
            </h2>
            <Button
              variant="secondary"
              size="sm"
              onClick={async () => {
                await markAllAsRead()
                cache.invalidateQueries({ queryKey: ['vendor-notifications'] })
                cache.invalidateQueries({ queryKey: ['notif-count'] })
              }}
            >
              Marcar como leídas
            </Button>
          </div>

          {notifs.length === 0 ? (
            <div className="text-center py-12">
              <Bell
                size={36}
                className="mx-auto mb-3 text-[var(--color-border-strong)]"
                strokeWidth={1.5}
              />
              <p className="font-sans text-sm text-[var(--color-text-muted)]">Sin notificaciones.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {notifs.map(n => (
                <article
                  key={n.id}
                  className="border border-[var(--color-border)] rounded-[var(--radius-lg)] p-4 bg-[var(--color-surface)]"
                >
                  <strong className="font-display font-semibold text-sm text-[var(--color-text-primary)]">
                    {n.titulo}
                  </strong>
                  <p className="font-sans text-sm text-[var(--color-text-secondary)] mt-1">
                    {n.mensaje}
                  </p>
                  <small className="font-sans text-xs text-[var(--color-text-muted)] mt-2 block">
                    {formatDate(n.fecha)}
                  </small>
                </article>
              ))}
            </div>
          )}
        </section>
      )}
    </main>
  )
}
