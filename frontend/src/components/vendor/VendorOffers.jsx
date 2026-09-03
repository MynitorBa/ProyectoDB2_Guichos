import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { AlertCircle } from 'lucide-react'
import api from '../../api/client'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Badge } from '../ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { formatQ } from '../../lib/utils'

const OFFER_STATE_BADGE = {
  activa: 'success',
  pausada: 'warning',
  descontinuada: 'default',
  borrador: 'default',
}

export function VendorOffers() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [state, setState] = useState('todos')
  const { data, isLoading, isError } = useQuery({
    queryKey: ['vendor-offers', search, page, state],
    queryFn: () => api.get('/vendor/offers', { params: { q: search, page, ...(state !== 'todos' && { estado: state }) } }).then(r => r.data),
  })

  return (
    <section className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold font-display">Mis productos y ofertas</h2>
        <p className="text-sm text-[var(--color-text-secondary)] mt-1">
          Consulta cada variante y administra tu precio y existencias. Los productos nuevos requieren aprobación.
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Input
          aria-label="Buscar mis ofertas"
          placeholder="Buscar producto o SKU…"
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(1) }}
          className="max-w-xs"
        />
        <Select value={state} onValueChange={v => { setState(v); setPage(1) }}>
          <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
          <SelectContent>
            {['todos', 'activa', 'pausada', 'descontinuada', 'borrador'].map(s => (
              <SelectItem key={s} value={s}>
                {s === 'todos' ? 'Todos los estados' : s.charAt(0).toUpperCase() + s.slice(1)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <div className="grid md:grid-cols-2 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="border border-[var(--color-border)] rounded-xl p-4 flex gap-4 animate-pulse">
              <div className="w-20 h-20 bg-[var(--color-border)] rounded-xl flex-shrink-0" />
              <div className="flex-1 space-y-2 py-1">
                <div className="h-4 bg-[var(--color-border)] rounded w-3/4" />
                <div className="h-3 bg-[var(--color-border)] rounded w-1/2" />
                <div className="h-3 bg-[var(--color-border)] rounded w-1/3" />
              </div>
            </div>
          ))}
        </div>
      ) : isError ? (
        <p role="alert" className="text-[var(--color-error)]">No se pudieron cargar tus ofertas.</p>
      ) : (
        <div className="grid md:grid-cols-2 gap-3">
          {data?.items.map(o => (
            <Link
              key={o.id}
              to={`/vendor/offers/${o.id}`}
              className="flex gap-4 border border-[var(--color-border)] p-4 rounded-xl bg-[var(--color-surface)] hover:border-[var(--color-action)] hover:shadow-[var(--shadow-md)] transition-all group"
            >
              {o.imagen
                ? <img alt="" src={o.imagen} className="w-20 h-20 object-contain rounded-xl flex-shrink-0 bg-[var(--color-background)]" />
                : <div className="w-20 h-20 bg-[var(--color-background)] rounded-xl flex-shrink-0" />
              }
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-semibold text-sm group-hover:text-[var(--color-action)] transition-colors truncate">
                    {o.producto_nombre}
                  </h3>
                  <Badge variant={OFFER_STATE_BADGE[o.estado] || 'default'} className="flex-shrink-0">{o.estado}</Badge>
                </div>
                <p className="text-xs text-[var(--color-text-secondary)] mt-0.5 truncate">
                  {Object.entries(o.atributos).map(([k, v]) => `${k}: ${v}`).join(' · ') || 'Variante predeterminada'}
                </p>
                <p className="text-xs font-mono text-[var(--color-text-muted)] mt-0.5">{o.sku}</p>
                <p className="text-sm font-semibold mt-1.5">
                  {formatQ(o.precio)}
                  <span className="font-normal text-[var(--color-text-secondary)]"> · {o.stock} disponibles</span>
                </p>
                {o.producto_estado !== 'activo' && (
                  <p className="flex items-center gap-1 text-xs text-[var(--color-error)] mt-1">
                    <AlertCircle size={11} />
                    Producto {o.producto_estado}: no visible en catálogo.
                  </p>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}

      {!isLoading && !data?.items.length && (
        <p className="text-center text-[var(--color-text-muted)] py-10">No hay ofertas con estos filtros.</p>
      )}

      <div className="flex justify-center items-center gap-3 pt-2">
        <Button variant="secondary" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Anterior</Button>
        <span className="text-sm text-[var(--color-text-secondary)]">{page} / {data?.total_pages || 1}</span>
        <Button variant="secondary" disabled={page >= (data?.total_pages || 1)} onClick={() => setPage(p => p + 1)}>Siguiente</Button>
      </div>
    </section>
  )
}

function OfferForm({ offer }) {
  const [price, setPrice] = useState(offer.precio)
  const [stock, setStock] = useState(offer.existencias)
  const [state, setState] = useState(offer.estado)
  const cache = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => api.patch(`/vendor/offers/${offer.id}`, { precio: Number(price), stock: Number(stock), estado: state, version: offer.version }),
    onSuccess: () => {
      toast.success('Oferta actualizada con historial.')
      cache.invalidateQueries({ queryKey: ['vendor-offers'] })
      cache.invalidateQueries({ queryKey: ['vendor-offer'] })
    },
    onError: e => toast.error(e.response?.data?.detail || 'No se pudo guardar.'),
  })
  const editable = ['activa', 'pausada'].includes(offer.estado)

  return (
    <form className="space-y-6" onSubmit={e => { e.preventDefault(); mutation.mutate() }}>
      <div className="flex gap-5 items-center">
        {offer.imagen && (
          <img alt="" src={offer.imagen} className="w-28 h-28 object-contain rounded-xl border border-[var(--color-border)] bg-[var(--color-background)] flex-shrink-0" />
        )}
        <div>
          <h1 className="text-2xl font-bold font-display">{offer.producto_nombre}</h1>
          <p className="text-[var(--color-text-secondary)] mt-1">
            {Object.entries(offer.atributos).map(([k, v]) => `${k}: ${v}`).join(' · ') || 'Variante predeterminada'}
          </p>
          <p className="font-mono text-sm text-[var(--color-text-muted)] mt-0.5">{offer.sku}</p>
        </div>
      </div>

      <div className="border border-[var(--color-border)] rounded-xl p-5 space-y-5 bg-[var(--color-surface)]">
        <div className="grid sm:grid-cols-3 gap-5">
          <div className="space-y-1.5">
            <Label>Precio (GTQ)</Label>
            <Input required disabled={!editable} type="number" min="0.01" step="0.01" value={price} onChange={e => setPrice(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Existencias totales actuales</Label>
            <Input required disabled={!editable} type="number" min={offer.reservado} max="2147483647" step="1" value={stock} onChange={e => setStock(e.target.value)} />
            <p className="text-xs text-[var(--color-text-muted)]">Reservadas: {offer.reservado} · Disponibles: {offer.stock}</p>
          </div>
          <div className="space-y-1.5">
            <Label>Estado de mi oferta</Label>
            <Select disabled={!editable} value={state} onValueChange={setState}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {['activa', 'pausada', ...(!editable ? [offer.estado] : [])].map(s => (
                  <SelectItem key={s} value={s}>{s}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <p className="text-xs text-[var(--color-text-secondary)] bg-[var(--color-background)] rounded-lg px-3 py-2.5">
          Las existencias son el saldo total, no una cantidad para sumar. Para agregar 10 a un saldo de 20, escribe 30. El precio y el inventario conservarán historial.
        </p>
      </div>

      {editable ? (
        <Button loading={mutation.isPending} type="submit">Guardar cambios</Button>
      ) : (
        <div className="flex items-start gap-2 bg-[var(--color-warning-light)] border border-[var(--color-warning)] rounded-xl px-4 py-3">
          <AlertCircle size={15} className="text-[var(--color-warning)] flex-shrink-0 mt-0.5" />
          <p className="text-sm text-[var(--color-warning)]">Esta oferta requiere revisión del administrador para volver a publicarse.</p>
        </div>
      )}
    </form>
  )
}

export default function VendorOfferPage() {
  const { id } = useParams()
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['vendor-offer', id],
    queryFn: () => api.get('/vendor/offers', { params: { oferta_id: id } }).then(r => r.data.items[0]),
  })
  return (
    <main className="max-w-5xl mx-auto p-6 space-y-6">
      <Link to="/vendor?tab=offers" className="text-sm text-[var(--color-action)] hover:underline">← Mis ofertas</Link>
      {isLoading ? (
        <p className="text-[var(--color-text-secondary)]">Cargando…</p>
      ) : isError || !data ? (
        <p role="alert" className="text-[var(--color-error)]">Oferta no encontrada o sin permiso.</p>
      ) : (
        <>
          <OfferForm key={`${data.id}-${data.version}`} offer={data} />
          <Button variant="secondary" onClick={() => refetch()}>Recargar datos actuales</Button>
        </>
      )}
    </main>
  )
}
