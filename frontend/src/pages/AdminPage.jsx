import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { BarChart2, Package, History, Users, ShieldCheck, ShoppingBag, User } from 'lucide-react'
import { toast } from 'sonner'
import { getCatalogStats, getProducts } from '../api/products'
import { getAdminUsers, updateUserRoles } from '../api/admin'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Skeleton } from '../components/ui/skeleton'
import { Separator } from '../components/ui/separator'
import { formatQ } from '../lib/utils'
import { cn } from '../lib/utils'

const NAV_ITEMS = [
  { id: 'stats',    label: 'Estadísticas', icon: BarChart2 },
  { id: 'products', label: 'Productos',    icon: Package   },
  { id: 'users',    label: 'Usuarios',     icon: Users     },
]

const ROLE_META = {
  administrador: { label: 'Admin',    Icon: ShieldCheck,   active: 'bg-[var(--color-action)] text-white border-[var(--color-action)]',    inactive: 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-action)] hover:text-[var(--color-action)]' },
  vendedor:      { label: 'Vendedor', Icon: ShoppingBag,   active: 'bg-[var(--color-jade)] text-white border-[var(--color-jade)]',          inactive: 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-jade)] hover:text-[var(--color-jade)]' },
  comprador:     { label: 'Comprador', Icon: User,          active: 'bg-[var(--color-border-strong)] text-[var(--color-text-primary)] border-[var(--color-border-strong)]', inactive: 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-border-strong)] hover:text-[var(--color-text-primary)]' },
}
const ALL_ROLES = ['comprador', 'vendedor', 'administrador']

function StatCard({ label, value, sub }) {
  return (
    <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5">
      <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-1">
        {label}
      </p>
      <p className="font-mono font-bold text-3xl text-[var(--color-text-primary)]">{value}</p>
      {sub && (
        <p className="font-sans text-xs text-[var(--color-text-muted)] mt-1">{sub}</p>
      )}
    </div>
  )
}

function StatsSection() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['catalog-stats'],
    queryFn: () => getCatalogStats().then((r) => r.data[0]),
  })

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }

  if (isError || !data) {
    return (
      <p className="font-sans text-sm text-[var(--color-error)]">
        Error al cargar estadísticas.
      </p>
    )
  }

  const global = data.resumen_global?.[0] || {}
  const porCategoria = data.estadisticas_por_categoria || []
  const topProductos = data.top_productos_precio || []

  const chartData = porCategoria.map((cat) => ({
    name: cat.categoria_nombre?.split(' ')[0] || cat._id,
    promedio: Math.round(cat.precio_promedio || 0),
  }))

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          label="Total de productos"
          value={global.total_productos ?? '—'}
        />
        <StatCard
          label="Disponibles"
          value={global.total_disponibles ?? '—'}
          sub={global.total_productos ? `${Math.round((global.total_disponibles / global.total_productos) * 100)}% del catálogo` : undefined}
        />
        <StatCard
          label="Precio promedio global"
          value={global.precio_promedio_global ? formatQ(global.precio_promedio_global) : '—'}
        />
      </div>

      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5">
        <h3 className="font-display font-semibold text-base text-[var(--color-text-primary)] mb-4">
          Precio promedio por categoría
        </h3>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 11, fontFamily: 'var(--font-sans)', fill: 'var(--color-text-muted)' }}
            />
            <YAxis
              tick={{ fontSize: 11, fontFamily: 'var(--font-mono)', fill: 'var(--color-text-muted)' }}
              tickFormatter={(v) => `Q${v}`}
            />
            <Tooltip
              formatter={(v) => [formatQ(v), 'Precio promedio']}
              contentStyle={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-md)',
                fontFamily: 'var(--font-sans)',
                fontSize: 12,
              }}
            />
            <Bar dataKey="promedio" fill="var(--color-action)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {topProductos.length > 0 && (
        <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
          <div className="px-5 py-4 border-b border-[var(--color-border)]">
            <h3 className="font-display font-semibold text-base text-[var(--color-text-primary)]">
              Top 5 productos más caros
            </h3>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[var(--color-background)]">
                {['Nombre', 'Categoría', 'Precio'].map((h) => (
                  <th
                    key={h}
                    className="px-5 py-3 text-left font-sans font-semibold text-xs uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)]"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {topProductos.slice(0, 5).map((prod, idx) => (
                <tr
                  key={prod._id}
                  className={idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]'}
                >
                  <td className="px-5 py-3 font-display font-semibold text-[var(--color-text-primary)]">
                    {prod.nombre}
                  </td>
                  <td className="px-5 py-3 font-sans text-[var(--color-text-secondary)]">
                    {prod.categoria}
                  </td>
                  <td className="px-5 py-3 font-mono font-bold text-[var(--color-text-primary)]">
                    {formatQ(prod.precio)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {porCategoria.length > 0 && (
        <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
          <div className="px-5 py-4 border-b border-[var(--color-border)]">
            <h3 className="font-display font-semibold text-base text-[var(--color-text-primary)]">
              Estadísticas por categoría
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-[var(--color-background)]">
                  {['Categoría', 'Total', 'Disponibles', 'Precio mín', 'Precio máx', 'Promedio'].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left font-sans font-semibold text-xs uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)] whitespace-nowrap"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {porCategoria.map((cat, idx) => (
                  <tr
                    key={cat._id}
                    className={idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]'}
                  >
                    <td className="px-4 py-3 font-display font-semibold text-[var(--color-text-primary)]">
                      {cat.categoria_nombre}
                    </td>
                    <td className="px-4 py-3 font-mono text-[var(--color-text-primary)]">
                      {cat.total_productos}
                    </td>
                    <td className="px-4 py-3 font-mono text-[var(--color-text-primary)]">
                      {cat.disponibles}
                    </td>
                    <td className="px-4 py-3 font-mono text-[var(--color-text-primary)]">
                      {formatQ(cat.precio_minimo)}
                    </td>
                    <td className="px-4 py-3 font-mono text-[var(--color-text-primary)]">
                      {formatQ(cat.precio_maximo)}
                    </td>
                    <td className="px-4 py-3 font-mono font-semibold text-[var(--color-text-primary)]">
                      {formatQ(cat.precio_promedio)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function ProductsSection() {
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 15

  const { data, isLoading } = useQuery({
    queryKey: ['admin-products', page],
    queryFn: () => getProducts({ page, page_size: PAGE_SIZE }).then((r) => r.data),
    placeholderData: keepPreviousData,
  })

  const products = data?.items || []
  const totalPages = data?.total_pages || 1

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    )
  }

  return (
    <div>
      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[var(--color-background)]">
                {['Nombre', 'Categoría', 'Precio', 'Disponible', 'Acciones'].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-3 text-left font-sans font-semibold text-xs uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)]"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {products.map((prod, idx) => (
                <tr
                  key={prod._id}
                  className={cn(
                    'border-b border-[var(--color-border)] last:border-0',
                    idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]'
                  )}
                >
                  <td className="px-4 py-3 font-display font-semibold text-[var(--color-text-primary)] max-w-[220px]">
                    <span className="line-clamp-1">{prod.nombre}</span>
                    <span className="font-mono font-normal text-[10px] text-[var(--color-text-muted)] block">
                      {prod.sku}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-sans text-[var(--color-text-secondary)]">
                    {prod.categoria?.nombre || '—'}
                  </td>
                  <td className="px-4 py-3 font-mono font-semibold text-[var(--color-text-primary)]">
                    {formatQ(prod.precio)}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={prod.disponible ? 'success' : 'error'}>
                      {prod.disponible ? 'Sí' : 'No'}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <Button variant="ghost" size="sm" asChild>
                      <Link to={`/admin/products/${prod._id}/history`}>
                        <History size={13} /> Historial
                      </Link>
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-5">
          <Button
            variant="secondary"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            Anterior
          </Button>
          <span className="font-sans text-sm text-[var(--color-text-secondary)]">
            {page} / {totalPages}
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            Siguiente
          </Button>
        </div>
      )}
    </div>
  )
}

function UsersSection() {
  const [page, setPage] = useState(1)
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['admin-users', page],
    queryFn: () => getAdminUsers(page).then((r) => r.data),
    placeholderData: keepPreviousData,
  })

  const mutation = useMutation({
    mutationFn: ({ userId, roles }) => updateUserRoles(userId, roles),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-users'] }),
    onError: (err) => toast.error(err?.response?.data?.detail || 'No se pudo actualizar los roles.'),
  })

  function toggleRole(user, role) {
    const current = new Set(user.roles)
    if (current.has(role)) current.delete(role)
    else current.add(role)
    mutation.mutate({ userId: user.id, roles: [...current] })
  }

  const users = data?.items || []
  const totalPages = data?.total_pages || 1

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    )
  }

  return (
    <div>
      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[var(--color-background)]">
                {['Usuario', 'Email', 'Estado', 'Roles (clic para cambiar)'].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-3 text-left font-sans font-semibold text-xs uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)] whitespace-nowrap"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.map((user, idx) => (
                <tr
                  key={user.id}
                  className={cn(
                    'border-b border-[var(--color-border)] last:border-0',
                    idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]'
                  )}
                >
                  <td className="px-4 py-3">
                    <p className="font-display font-semibold text-[var(--color-text-primary)]">
                      {user.nombre} {user.apellido}
                    </p>
                    <p className="font-mono text-[10px] text-[var(--color-text-muted)]">#{user.id}</p>
                  </td>
                  <td className="px-4 py-3 font-sans text-[var(--color-text-secondary)] text-xs">
                    {user.email}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={user.estado === 'activo' ? 'success' : 'error'}>
                      {user.estado}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1.5">
                      {ALL_ROLES.map((role) => {
                        const meta = ROLE_META[role]
                        const { Icon } = meta
                        const hasRole = user.roles.includes(role)
                        return (
                          <button
                            key={role}
                            onClick={() => toggleRole(user, role)}
                            disabled={mutation.isPending}
                            className={cn(
                              'inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-sans font-semibold border transition-all duration-150 disabled:opacity-50',
                              hasRole ? meta.active : meta.inactive
                            )}
                          >
                            <Icon size={11} strokeWidth={2} />
                            {meta.label}
                          </button>
                        )
                      })}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-5">
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Anterior
          </Button>
          <span className="font-sans text-sm text-[var(--color-text-secondary)]">{page} / {totalPages}</span>
          <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
            Siguiente
          </Button>
        </div>
      )}
    </div>
  )
}

export default function AdminPage() {
  const [activeSection, setActiveSection] = useState('stats')

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <div className="flex">
        <aside className="w-56 shrink-0 min-h-screen border-r border-[var(--color-border)] bg-[var(--color-surface)] pt-8">
          <div className="px-5 mb-6">
            <h1 className="font-display font-bold text-base text-[var(--color-text-primary)]">
              Panel Admin
            </h1>
            <p className="font-sans text-xs text-[var(--color-text-muted)] mt-0.5">TiendaYa</p>
          </div>
          <Separator />
          <nav className="p-3 mt-2 space-y-1">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveSection(item.id)}
                  className={cn(
                    'w-full flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-md)] text-sm font-sans font-medium transition-colors text-left',
                    activeSection === item.id
                      ? 'bg-[var(--color-action)] text-white'
                      : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] hover:text-[var(--color-text-primary)]'
                  )}
                >
                  <Icon size={16} />
                  {item.label}
                </button>
              )
            })}
          </nav>
        </aside>

        <main className="flex-1 min-w-0 p-8">
          <h2 className="font-display font-bold text-2xl text-[var(--color-text-primary)] mb-6">
            {NAV_ITEMS.find((n) => n.id === activeSection)?.label}
          </h2>
          {activeSection === 'stats' && <StatsSection />}
          {activeSection === 'products' && <ProductsSection />}
          {activeSection === 'users' && <UsersSection />}
        </main>
      </div>
    </div>
  )
}
