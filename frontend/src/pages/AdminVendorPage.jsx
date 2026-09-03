import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Star } from 'lucide-react'
import api from '../api/client'
import { getAdminVendors, setVendorProfile, setTiendayaVendor } from '../api/admin'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Badge } from '../components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { formatQ, formatDate } from '../lib/utils'
import { orderStateLabel } from './OrderWorkspacePage'

const ORDER_STATE_BADGE = {
  pendiente:         'warning',
  confirmado:        'action',
  preparando:        'action',
  enviado_parcial:   'jade',
  entregado_parcial: 'jade',
  entregado:         'success',
  cancelado:         'error',
  reembolsado:       'default',
}

const VERIFICATION_BADGE = {
  verificado: 'success',
  pendiente: 'warning',
  rechazado: 'error',
}

export function AdminVendorsSection() {
  const [search, setSearch] = useState('')
  const { data = [], isLoading, isError } = useQuery({
    queryKey: ['admin-vendors'],
    queryFn: () => getAdminVendors().then(r => r.data),
  })
  const filtered = data.filter(v =>
    [v.nombre_comercial, v.nombre_completo, v.email].join(' ').toLowerCase().includes(search.toLowerCase())
  )

  return (
    <section className="space-y-4">
      <Input
        aria-label="Buscar vendedor"
        placeholder="Buscar negocio, persona o correo…"
        value={search}
        onChange={e => setSearch(e.target.value)}
        className="max-w-sm"
      />
      {isLoading ? (
        <p className="text-[var(--color-text-secondary)]">Cargando…</p>
      ) : isError ? (
        <p className="text-[var(--color-error)]">No se pudieron consultar los vendedores.</p>
      ) : (
        <div className="space-y-2">
          {filtered.map(v => (
            <Link
              key={v.usuario_id}
              to={v.vendedor_id ? `/admin/vendors/${v.vendedor_id}` : `/admin/users/${v.usuario_id}`}
              className="flex items-center justify-between border border-[var(--color-border)] rounded-xl px-5 py-4 bg-[var(--color-surface)] hover:border-[var(--color-action)] hover:shadow-[var(--shadow-sm)] transition-all group"
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold group-hover:text-[var(--color-action)] transition-colors">
                    {v.nombre_comercial || v.nombre_completo}
                  </span>
                  {v.es_tiendaya && (
                    <span className="flex items-center gap-1 text-xs font-medium text-[var(--color-warning)] bg-[var(--color-warning-light)] px-2 py-0.5 rounded-full">
                      <Star size={10} /> TiendaYa
                    </span>
                  )}
                </div>
                <p className="text-sm text-[var(--color-text-secondary)] mt-0.5">
                  {v.email} · {v.nit || 'Sin perfil comercial'}
                </p>
              </div>
              <Badge variant={VERIFICATION_BADGE[v.estado_verificacion] || 'default'}>
                {v.estado_verificacion}
              </Badge>
            </Link>
          ))}
          {!filtered.length && (
            <p className="text-center text-[var(--color-text-muted)] py-10">No hay vendedores con ese filtro.</p>
          )}
        </div>
      )}
    </section>
  )
}

function Profile({ vendor }) {
  const [name, setName] = useState(vendor.nombre_comercial)
  const [nit, setNit] = useState(vendor.nit)
  const cache = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => setVendorProfile(vendor.usuario_id, { nombre_comercial: name, nit }),
    onSuccess: () => {
      toast.success('Perfil actualizado.')
      cache.invalidateQueries({ queryKey: ['admin-vendors'] })
      cache.invalidateQueries({ queryKey: ['admin-vendor'] })
    },
    onError: e => toast.error(e.response?.data?.detail || 'No se pudo guardar.'),
  })
  const mark = useMutation({
    mutationFn: () => setTiendayaVendor(vendor.id),
    onSuccess: () => {
      cache.invalidateQueries({ queryKey: ['admin-vendors'] })
      cache.invalidateQueries({ queryKey: ['admin-vendor'] })
    },
    onError: e => toast.error(e.response?.data?.detail || 'No se pudo cambiar la marca.'),
  })

  return (
    <section className="border border-[var(--color-border)] rounded-xl p-6 space-y-5 bg-[var(--color-surface)]">
      <form onSubmit={e => { e.preventDefault(); mutation.mutate() }} className="grid sm:grid-cols-3 gap-4 items-end">
        <div className="space-y-1.5">
          <Label>Nombre comercial</Label>
          <Input required value={name} onChange={e => setName(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label>NIT</Label>
          <Input required value={nit} onChange={e => setNit(e.target.value)} />
        </div>
        <Button type="submit" loading={mutation.isPending}>Guardar perfil</Button>
      </form>
      <div className="flex items-center justify-between border-t border-[var(--color-border)] pt-4">
        <div>
          <p className="text-sm font-medium">Estado de verificación</p>
          <Badge variant={VERIFICATION_BADGE[vendor.estado_verificacion] || 'default'} className="mt-1">
            {vendor.estado_verificacion}
          </Badge>
        </div>
        <Button variant="secondary" loading={mark.isPending} onClick={() => mark.mutate()}>
          {vendor.es_tiendaya ? 'Quitar marca TiendaYa' : 'Marcar como TiendaYa'}
        </Button>
      </div>
    </section>
  )
}

export default function AdminVendorPage() {
  const { id } = useParams()
  const [ordersPage, setOrdersPage] = useState(1)
  const [offersPage, setOffersPage] = useState(1)
  const [state, setState] = useState('todos')
  const { data: v, isLoading, isError } = useQuery({
    queryKey: ['admin-vendor', id, ordersPage, offersPage, state],
    queryFn: () => api.get(`/admin/vendors/${id}`, {
      params: { orders_page: ordersPage, offers_page: offersPage, ...(state !== 'todos' && { estado: state }) },
    }).then(r => r.data),
  })

  return (
    <main className="max-w-6xl mx-auto p-6 space-y-6">
      <Link to="/admin?section=vendors" className="text-sm text-[var(--color-action)] hover:underline">← Vendedores</Link>
      {isLoading ? (
        <p className="text-[var(--color-text-secondary)]">Cargando…</p>
      ) : isError ? (
        <p role="alert" className="text-[var(--color-error)]">No se pudo cargar el vendedor.</p>
      ) : (
        <>
          <header className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold font-display">{v.nombre_comercial}</h1>
              <Link to={`/admin/users/${v.usuario_id}`} className="text-sm text-[var(--color-action)] hover:underline mt-1 block">
                Cuenta: {v.email}
              </Link>
            </div>
            {v.es_tiendaya && (
              <span className="flex items-center gap-1.5 text-sm font-medium text-[var(--color-warning)] bg-[var(--color-warning-light)] px-3 py-1.5 rounded-full flex-shrink-0">
                <Star size={12} /> Vendedor TiendaYa
              </span>
            )}
          </header>

          <Profile key={v.id} vendor={v} />

          <section className="space-y-4">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <h2 className="text-xl font-semibold font-display">Pedidos del vendedor</h2>
              <Select value={state} onValueChange={s => { setState(s); setOrdersPage(1) }}>
                <SelectTrigger className="w-56"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="todos">Todos los estados</SelectItem>
                  {Object.keys(v.pedidos_por_estado).map(s => (
                    <SelectItem key={s} value={s}>{orderStateLabel(s)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(v.pedidos_por_estado).map(([s, n]) => (
                <span key={s} className="border border-[var(--color-border)] rounded-lg px-3 py-1.5 text-sm bg-[var(--color-surface)]">
                  <span className="text-[var(--color-text-secondary)]">{orderStateLabel(s)}:</span>{' '}
                  <strong>{n}</strong>
                </span>
              ))}
            </div>
            <div className="space-y-2">
              {v.pedidos.map(p => (
                <Link
                  key={p.subpedido_id}
                  to={`/admin/orders/${p.id}`}
                  className="flex items-center justify-between border border-[var(--color-border)] rounded-xl px-4 py-3 bg-[var(--color-surface)] hover:border-[var(--color-action)] transition-colors"
                >
                  <div>
                    <span className="font-medium">Pedido #{p.id}</span>
                    <span className="text-sm text-[var(--color-text-secondary)] ml-2">{formatDate(p.fecha)}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-semibold text-sm">{formatQ(p.subtotal)}</span>
                    <Badge variant={ORDER_STATE_BADGE[p.estado] || 'default'}>{orderStateLabel(p.estado)}</Badge>
                  </div>
                </Link>
              ))}
            </div>
            <div className="flex justify-center items-center gap-3">
              <Button variant="secondary" disabled={ordersPage === 1} onClick={() => setOrdersPage(p => p - 1)}>Anterior</Button>
              <span className="text-sm text-[var(--color-text-secondary)]">{ordersPage} / {v.pedidos_pages}</span>
              <Button variant="secondary" disabled={ordersPage >= v.pedidos_pages} onClick={() => setOrdersPage(p => p + 1)}>Siguiente</Button>
            </div>
          </section>

          <section className="space-y-4">
            <h2 className="text-xl font-semibold font-display">Ofertas y productos</h2>
            <div className="space-y-2">
              {v.ofertas.map(o => (
                <Link
                  key={o.id}
                  to={`/admin/products/${o.producto_ref}?tab=offers`}
                  className="flex items-center justify-between border border-[var(--color-border)] rounded-xl px-4 py-3 bg-[var(--color-surface)] hover:border-[var(--color-action)] transition-colors group"
                >
                  <div>
                    <span className="font-medium group-hover:text-[var(--color-action)] transition-colors">{o.producto_nombre}</span>
                    <span className="text-xs font-mono text-[var(--color-text-muted)] ml-2">{o.sku}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-sm">
                      {formatQ(o.precio)}{' '}
                      <span className="text-[var(--color-text-secondary)]">· {o.stock} disponibles</span>
                    </span>
                    <Badge variant={o.estado === 'activa' ? 'success' : 'default'}>{o.estado}</Badge>
                  </div>
                </Link>
              ))}
            </div>
            <div className="flex justify-center items-center gap-3">
              <Button variant="secondary" disabled={offersPage === 1} onClick={() => setOffersPage(p => p - 1)}>Anterior</Button>
              <span className="text-sm text-[var(--color-text-secondary)]">{offersPage} / {v.ofertas_pages}</span>
              <Button variant="secondary" disabled={offersPage >= v.ofertas_pages} onClick={() => setOffersPage(p => p + 1)}>Siguiente</Button>
            </div>
          </section>
        </>
      )}
    </main>
  )
}
