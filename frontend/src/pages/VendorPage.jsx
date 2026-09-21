import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, LineChart, Line } from 'recharts'
import { Bell, Package, ClipboardList, Store, TrendingUp, Paintbrush } from 'lucide-react'
import { getVendorStats, getVendorOrders } from '../api/vendor'
import { getNotifications, markAllAsRead } from '../api/notifications'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../components/ui/select'
import { Badge } from '../components/ui/badge'
import { formatQ, formatDate, cn } from '../lib/utils'
import { CatalogRequestsSection } from '../components/vendor/CatalogRequestsSection'
import { VendorOffers } from '../components/vendor/VendorOffers'
import { orderStateLabel } from './OrderWorkspacePage'
import { getVendorAnalyticsProducts, getVendorProductTrend, getVendorTrends } from '../api/analytics'
import ProductPicker from '../components/ProductPicker'

function mondayNow() {
  const now = new Date()
  now.setDate(now.getDate() - ((now.getDay() + 6) % 7))
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

function moveWeek(week, amount) {
  const value = new Date(`${week}T12:00:00`)
  value.setDate(value.getDate() + amount * 7)
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
}

const loadVendorAnalyticsProducts = (params) => getVendorAnalyticsProducts(params)
const TREND_COLORS = ['var(--color-action)', 'var(--color-jade)', '#f59e0b', '#8b5cf6', '#64748b']

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
  { key: 'trends',        label: 'Mis tendencias',          icon: TrendingUp    },
  { key: 'requests',      label: 'Solicitudes de catálogo', icon: Store         },
  { key: 'store',         label: 'Mi tienda',               icon: Paintbrush    },
  { key: 'notifications', label: 'Notificaciones',          icon: Bell          },
]

export default function VendorPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'orders'
  const [page, setPage] = useState(1)
  const [analyticsWeek, setAnalyticsWeek] = useState(mondayNow)
  const [comparisonWeeks, setComparisonWeeks] = useState(1)
  const [onlyWithoutSales, setOnlyWithoutSales] = useState(false)
  const [selectedTrendProduct, setSelectedTrendProduct] = useState(null)
  const [trendFrom, setTrendFrom] = useState(() => moveWeek(mondayNow(), -11))
  const [trendTo, setTrendTo] = useState(mondayNow)
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
  const { data: trends, isLoading: trendsLoading, error: trendsError } = useQuery({
    queryKey: ['vendor-cassandra-trends', analyticsWeek, comparisonWeeks, onlyWithoutSales],
    queryFn: () => getVendorTrends(analyticsWeek, comparisonWeeks, onlyWithoutSales).then(r => r.data),
    enabled: tab === 'trends',
    retry: false,
  })
  const { data: productTrend, isLoading: productTrendLoading, error: productTrendError } = useQuery({
    queryKey: ['vendor-product-trend', selectedTrendProduct?._id, trendFrom, trendTo],
    queryFn: () => getVendorProductTrend(selectedTrendProduct._id, trendFrom, trendTo).then(r => r.data),
    enabled: tab === 'trends' && !!selectedTrendProduct?._id && trendFrom <= trendTo,
    retry: false,
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
      {tab === 'store' && (
        <section className="space-y-4">
          <div>
            <h2 className="font-display font-semibold text-xl text-[var(--color-text-primary)]">Mi tienda</h2>
            <p className="font-sans text-sm text-[var(--color-text-secondary)] mt-1">
              Personaliza el aspecto de tu página pública: colores, fuentes, secciones y más.
            </p>
          </div>
          <div className="flex flex-col sm:flex-row gap-3">
            <Link to="/vendor/store/editor"
              className="inline-flex items-center gap-2 px-5 py-3 rounded-[var(--radius-lg)] font-display font-semibold text-sm text-white shadow-sm hover:opacity-90 transition-opacity"
              style={{ background: 'linear-gradient(135deg, var(--color-action), var(--color-jade))' }}>
              <Paintbrush size={16} /> Abrir editor de tienda
            </Link>
            {stats?.nombre_comercial && (
              <Link to={`/tienda/${stats.vendedor_id || ''}`} target="_blank"
                className="inline-flex items-center gap-2 px-5 py-3 rounded-[var(--radius-lg)] font-display font-semibold text-sm border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-primary)] hover:border-[var(--color-action)] transition-colors">
                <Store size={16} /> Ver mi tienda pública
              </Link>
            )}
          </div>
          <p className="font-sans text-xs text-[var(--color-text-muted)]">
            Los cambios se publican en tu tienda pública al hacer clic en "Guardar" dentro del editor.
          </p>
        </section>
      )}

      {tab === 'trends' && (
        <section className="space-y-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="font-display font-semibold text-xl">Rendimiento de mis ofertas</h2>
              <p className="font-sans text-sm text-[var(--color-text-secondary)] mt-1">Solo tus ventas pagadas y tus productos, por semana.</p>
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <label className="font-sans text-xs text-[var(--color-text-secondary)]">Semanas anteriores
                <Select value={String(comparisonWeeks)} onValueChange={value => setComparisonWeeks(Number(value))}>
                  <SelectTrigger className="mt-1 w-44"><SelectValue /></SelectTrigger>
                  <SelectContent>{[0,1,2,3,4].map(value => <SelectItem key={value} value={String(value)}>{value === 0 ? 'Solo la actual' : `${value} anterior${value > 1 ? 'es' : ''}`}</SelectItem>)}</SelectContent>
                </Select>
              </label>
              <label className="font-sans text-xs text-[var(--color-text-secondary)]">Semana que inicia
                <Input type="date" min="2020-01-06" step="7" value={analyticsWeek} onChange={e => setAnalyticsWeek(e.target.value)} className="mt-1" />
              </label>
            </div>
          </div>
          <div className="flex gap-2"><Button variant={!onlyWithoutSales ? 'primary' : 'secondary'} onClick={() => setOnlyWithoutSales(false)}>Con actividad</Button><Button variant={onlyWithoutSales ? 'primary' : 'secondary'} onClick={() => setOnlyWithoutSales(true)}>Sin ventas</Button></div>
          {trendsLoading ? <p className="text-sm text-[var(--color-text-muted)]">Cargando tendencias…</p> : trendsError ? (
            <p role="alert" className="text-sm text-[var(--color-error)]">{trendsError.response?.data?.detail || 'No se pudo consultar Cassandra.'}</p>
          ) : trends?.items?.length && onlyWithoutSales ? (
            <div className="overflow-x-auto border border-[var(--color-border)] rounded-[var(--radius-lg)]"><table className="w-full text-sm"><thead><tr className="bg-[var(--color-background)]">
              {['Oferta','Producto','SKU','Estado','Precio','Stock','Resultado'].map(header => <th key={header} className="px-3 py-2.5 text-left text-xs uppercase text-[var(--color-text-muted)]">{header}</th>)}
            </tr></thead><tbody>{trends.items.map(item => <tr key={item.oferta_id} className="border-t border-[var(--color-border)] bg-red-50">
              <td className="px-3 py-3 font-mono">#{item.oferta_id}</td><td className="px-3 py-3 font-semibold">{item.producto_nombre}</td><td className="px-3 py-3 font-mono">{item.sku}</td><td className="px-3 py-3 capitalize">{item.estado}</td><td className="px-3 py-3 font-mono">{formatQ(item.precio)}</td><td className="px-3 py-3 font-mono">{item.stock}</td><td className="px-3 py-3 font-semibold text-[var(--color-error)]">0 · Sin ventas</td>
            </tr>)}</tbody></table></div>
          ) : trends?.items?.length ? <>
            <div className="border border-[var(--color-border)] rounded-[var(--radius-lg)] bg-[var(--color-surface)] p-5">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={trends.items.slice(0, 10).map(item => ({ sku: item.sku, ...Object.fromEntries((item.semanas || []).map(value => [value.semana_inicio, value.unidades])) }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis dataKey="sku" tick={{ fontSize: 10 }} />
                  <YAxis allowDecimals={false} />
                  <Tooltip /><Legend />
                  {(trends.items[0]?.semanas || []).map((value, index) => <Bar key={value.semana_inicio} dataKey={value.semana_inicio} name={index === 0 ? `Actual · ${value.semana_inicio}` : `${index} sem. antes · ${value.semana_inicio}`} fill={TREND_COLORS[index]} radius={[4,4,0,0]} />)}
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="overflow-x-auto border border-[var(--color-border)] rounded-[var(--radius-lg)]">
              <table className="w-full text-sm"><thead><tr className="bg-[var(--color-background)]">
                {['Oferta','Producto','SKU',...(trends.items[0]?.semanas || []).map((_, index) => index === 0 ? 'Actual' : `Hace ${index} sem.`),'Ingreso neto','Flash'].map(h => <th key={h} className="px-3 py-2.5 text-left text-xs uppercase text-[var(--color-text-muted)]">{h}</th>)}
              </tr></thead><tbody>{trends.items.map(item => <tr key={item.oferta_id} className="border-t border-[var(--color-border)]">
                <td className="px-3 py-3 font-mono">#{item.oferta_id}</td><td className="px-3 py-3 font-semibold">{item.producto_nombre}</td>
                <td className="px-3 py-3 font-mono">{item.sku}</td>{(item.semanas || []).map(value => <td key={value.semana_inicio} className={cn('px-3 py-3 font-mono', value.unidades === 0 && 'text-[var(--color-error)]')}>{value.unidades}</td>)}
                <td className="px-3 py-3 font-mono">{formatQ(item.ingresos_netos)}</td><td className="px-3 py-3 font-mono">{item.unidades_flash}</td>
              </tr>)}</tbody></table>
            </div>
          </> : <p className="py-10 text-center text-sm text-[var(--color-text-muted)]">{onlyWithoutSales ? 'Todas tus ofertas registraron ventas esta semana.' : 'No tienes ventas pagadas en el período seleccionado.'}</p>}

          <div className="border-t border-[var(--color-border)] pt-6 space-y-5">
            <div><h3 className="font-display font-semibold text-lg">Seguimiento de uno de mis productos</h3><p className="text-sm text-[var(--color-text-secondary)]">La consulta suma únicamente las ofertas que te pertenecen.</p></div>
            <ProductPicker value={selectedTrendProduct} onSelect={setSelectedTrendProduct} loadProducts={loadVendorAnalyticsProducts} queryKey="vendor-analytics-product-picker" title="Seleccionar uno de mis productos" description="Solo aparecen productos asociados a tus ofertas." />
            <div className="grid gap-3 sm:grid-cols-2 max-w-xl"><label className="text-xs text-[var(--color-text-secondary)]">Desde (lunes)<Input type="date" min="2020-01-06" step="7" value={trendFrom} onChange={event => setTrendFrom(event.target.value)} className="mt-1" /></label><label className="text-xs text-[var(--color-text-secondary)]">Hasta (lunes)<Input type="date" min="2020-01-06" step="7" value={trendTo} onChange={event => setTrendTo(event.target.value)} className="mt-1" /></label></div>
            {trendFrom > trendTo ? <p className="text-sm text-[var(--color-error)]">La semana inicial no puede ser posterior a la final.</p> : !selectedTrendProduct ? <p className="py-8 text-center text-sm text-[var(--color-text-muted)]">Selecciona un producto para consultar su evolución.</p> : productTrendLoading ? <p className="text-sm text-[var(--color-text-muted)]">Cargando seguimiento…</p> : productTrendError ? <p className="text-sm text-[var(--color-error)]">{productTrendError.response?.data?.detail || 'No se pudo consultar el seguimiento.'}</p> : <>
              <div className="border border-[var(--color-border)] rounded-[var(--radius-lg)] bg-[var(--color-surface)] p-5"><h4 className="font-display font-semibold mb-4">{productTrend?.producto_nombre}</h4><ResponsiveContainer width="100%" height={260}><LineChart data={productTrend?.items || []}><CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" /><XAxis dataKey="semana_inicio" tick={{ fontSize: 10 }} /><YAxis allowDecimals={false} /><Tooltip /><Line type="monotone" dataKey="unidades" name="Unidades vendidas" stroke="var(--color-action)" strokeWidth={3} dot={{ r: 4 }} /></LineChart></ResponsiveContainer></div>
              <div className="overflow-x-auto border border-[var(--color-border)] rounded-[var(--radius-lg)]"><table className="w-full text-sm"><thead><tr className="bg-[var(--color-background)]">{['Semana','Unidades','Variación','Ingreso neto','Pedidos','Ofertas','Flash'].map(header => <th key={header} className="px-3 py-2.5 text-left text-xs uppercase text-[var(--color-text-muted)]">{header}</th>)}</tr></thead><tbody>{(productTrend?.items || []).map(item => <tr key={item.semana_inicio} className={cn('border-t border-[var(--color-border)]', item.unidades === 0 && 'bg-red-50')}><td className="px-3 py-3 font-semibold">{item.semana_inicio}</td><td className={cn('px-3 py-3 font-mono font-semibold', item.unidades === 0 && 'text-[var(--color-error)]')}>{item.unidades === 0 ? '0 · Sin ventas' : item.unidades}</td><td className={cn('px-3 py-3 font-mono', item.variacion_unidades < 0 && 'text-[var(--color-error)]')}>{item.variacion_unidades >= 0 ? '+' : ''}{item.variacion_unidades}</td><td className="px-3 py-3 font-mono">{formatQ(item.ingresos_netos)}</td><td className="px-3 py-3 font-mono">{item.pedidos}</td><td className="px-3 py-3 font-mono">{item.ofertas}</td><td className="px-3 py-3 font-mono">{item.unidades_flash}</td></tr>)}</tbody></table></div>
            </>}
          </div>
        </section>
      )}

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
