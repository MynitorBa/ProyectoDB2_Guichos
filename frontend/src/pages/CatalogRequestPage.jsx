import { useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { CheckCircle2 } from 'lucide-react'
import api from '../api/client'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { formatQ, formatDate } from '../lib/utils'

export const requestType = type => ({
  producto_nuevo: 'Producto nuevo',
  variante_nueva: 'Variante con oferta inicial',
  oferta_existente: 'Oferta existente',
}[type] || type)

const REQUEST_STATE_BADGE = {
  pendiente: 'warning',
  aprobada: 'success',
  rechazada: 'error',
  cancelada: 'default',
}

export default function CatalogRequestPage() {
  const { id } = useParams()
  const { pathname } = useLocation()
  const admin = pathname.startsWith('/admin')
  const prefix = admin ? 'admin' : 'vendor'
  const [note, setNote] = useState('')
  const cache = useQueryClient()
  const { data: r, isLoading, isError } = useQuery({
    queryKey: ['catalog-request', prefix, id],
    queryFn: () => api.get(`/${prefix}/catalog-requests/${id}`).then(res => res.data),
  })
  const action = useMutation({
    mutationFn: kind => kind === 'cancel'
      ? api.patch(`/vendor/catalog-requests/${id}/cancel`)
      : api.post(`/admin/catalog-requests/${id}/${kind}`, { observaciones: note }),
    onSuccess: () => {
      toast.success('Solicitud actualizada.')
      cache.invalidateQueries({ queryKey: ['catalog-request'] })
      cache.invalidateQueries({ queryKey: ['admin-catalog-requests'] })
      cache.invalidateQueries({ queryKey: ['vendor-catalog-requests'] })
      cache.invalidateQueries({ queryKey: ['vendor-offers'] })
    },
    onError: e => toast.error(e.response?.data?.detail || 'No se pudo actualizar.'),
  })

  return (
    <main className="max-w-5xl mx-auto p-6 space-y-6">
      <Link to={admin ? '/admin?section=requests' : '/vendor?tab=requests'} className="text-sm text-[var(--color-action)] hover:underline">
        ← Solicitudes
      </Link>

      {isLoading ? (
        <p className="text-[var(--color-text-secondary)]">Cargando solicitud…</p>
      ) : isError || !r ? (
        <p role="alert" className="text-[var(--color-error)]">No se encontró la solicitud o no tienes permiso.</p>
      ) : (
        <>
          <header className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold font-display">Solicitud #{r.id}</h1>
              <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                {requestType(r.tipo)} · {formatDate(r.fecha_creacion)}
              </p>
            </div>
            <Badge variant={REQUEST_STATE_BADGE[r.estado] || 'default'} className="flex-shrink-0 text-sm px-3 py-1">
              {r.estado}
            </Badge>
          </header>

          <section className="border border-[var(--color-border)] rounded-xl p-6 bg-[var(--color-surface)] space-y-5">
            <h2 className="text-xl font-semibold font-display">{r.nombre || r.producto_nombre}</h2>
            <div className="grid sm:grid-cols-3 gap-3">
              {[
                ['Vendedor', r.vendedor_nombre],
                ['Precio propuesto', formatQ(r.precio_propuesto)],
                ['Stock inicial', r.stock_propuesto],
              ].map(([label, value]) => (
                <div key={label} className="bg-[var(--color-background)] rounded-xl px-4 py-3">
                  <p className="text-xs text-[var(--color-text-muted)] mb-0.5">{label}</p>
                  <p className="font-semibold">{value}</p>
                </div>
              ))}
            </div>
            {r.descripcion && <p className="text-[var(--color-text-secondary)]">{r.descripcion}</p>}
            <div className="flex items-center gap-2 text-sm">
              <span className="text-[var(--color-text-muted)]">Categorías:</span>
              <span>{r.categorias.map(c => c.nombre).join(', ') || 'Las del producto existente'}</span>
            </div>
            <p className="text-xs text-[var(--color-text-muted)]">El SKU se generará automáticamente al aprobar.</p>
          </section>

          <section className="border border-[var(--color-border)] rounded-xl p-6 bg-[var(--color-surface)] space-y-4">
            <h2 className="font-semibold font-display">Atributos propuestos / variante</h2>
            {Object.keys(r.tipo === 'oferta_existente' ? r.variante_atributos : r.atributos).length > 0 ? (
              <dl className="grid sm:grid-cols-2 gap-3">
                {Object.entries(r.tipo === 'oferta_existente' ? r.variante_atributos : r.atributos).map(([k, v]) => (
                  <div key={k} className="bg-[var(--color-background)] rounded-xl px-4 py-3">
                    <dt className="text-xs text-[var(--color-text-muted)] mb-0.5">{k}</dt>
                    <dd className="font-medium">{String(v)}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="text-sm text-[var(--color-text-muted)]">Variante predeterminada sin atributos diferenciadores.</p>
            )}
          </section>

          {!!r.imagenes.length && (
            <section>
              <h2 className="font-semibold font-display mb-3">Imágenes propuestas</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {r.imagenes.map(image => (
                  <img
                    key={image.id}
                    src={image.url}
                    alt="Imagen propuesta"
                    className="h-40 object-contain border border-[var(--color-border)] rounded-xl w-full bg-[var(--color-surface)]"
                  />
                ))}
              </div>
            </section>
          )}

          <section className="border border-[var(--color-border)] rounded-xl p-6 bg-[var(--color-surface)] space-y-4">
            <h2 className="font-semibold font-display">Observaciones</h2>
            <div className="grid sm:grid-cols-2 gap-3">
              <div className="bg-[var(--color-background)] rounded-xl px-4 py-3">
                <p className="text-xs text-[var(--color-text-muted)] mb-1">Vendedor</p>
                <p className="text-sm">{r.observaciones_vendedor || 'Sin observaciones'}</p>
              </div>
              <div className="bg-[var(--color-background)] rounded-xl px-4 py-3">
                <p className="text-xs text-[var(--color-text-muted)] mb-1">Administrador</p>
                <p className="text-sm">{r.observaciones_admin || 'Sin observaciones'}</p>
              </div>
            </div>

            {r.estado === 'pendiente' && admin && (
              <div className="space-y-3 pt-1">
                <textarea
                  aria-label="Observaciones del administrador"
                  className="w-full p-3 border border-[var(--color-border)] rounded-xl bg-[var(--color-background)] text-sm resize-none focus-visible:outline-2 focus-visible:outline-[var(--color-action)] transition-colors"
                  rows={4}
                  value={note}
                  onChange={e => setNote(e.target.value)}
                  placeholder="Motivo de aprobación o rechazo…"
                />
                <div className="flex gap-3">
                  <Button disabled={action.isPending} onClick={() => action.mutate('approve')}>
                    Aprobar y publicar
                  </Button>
                  <Button
                    variant="destructive"
                    disabled={action.isPending}
                    onClick={() => {
                      if (!note.trim()) return toast.error('Indica un motivo de rechazo.')
                      action.mutate('reject')
                    }}
                  >
                    Rechazar
                  </Button>
                </div>
              </div>
            )}

            {r.estado === 'pendiente' && !admin && (
              <Button variant="secondary" disabled={action.isPending} onClick={() => action.mutate('cancel')}>
                Cancelar solicitud
              </Button>
            )}
          </section>

          {r.estado === 'aprobada' && (
            <div className="flex items-center gap-3 bg-[var(--color-success-light)] border border-[var(--color-success)] rounded-xl px-5 py-4">
              <CheckCircle2 size={18} className="text-[var(--color-success)] flex-shrink-0" />
              <p className="text-sm text-[var(--color-success)]">
                Solicitud aprobada · oferta #{r.oferta_id_resultado}.{' '}
                <Link
                  className="underline font-medium"
                  to={admin ? `/admin/products/${r.producto_ref_resultado}` : `/vendor/offers/${r.oferta_id_resultado}`}
                >
                  Abrir resultado →
                </Link>
              </p>
            </div>
          )}
        </>
      )}
    </main>
  )
}
