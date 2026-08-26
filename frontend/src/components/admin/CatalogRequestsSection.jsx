import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Eye, X } from 'lucide-react'
import { toast } from 'sonner'

import { approveCatalogRequest, getAdminCatalogRequests, rejectCatalogRequest } from '../../api/admin'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '../ui/dialog'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { Skeleton } from '../ui/skeleton'
import { formatDate, formatQ } from '../../lib/utils'

const STATUS = { pendiente: 'warning', aprobada: 'success', rechazada: 'error', cancelada: 'default' }

export function AdminCatalogRequestsSection() {
  const queryClient = useQueryClient()
  const [estado, setEstado] = useState('pendiente')
  const [selected, setSelected] = useState(null)
  const [observaciones, setObservaciones] = useState('')
  const { data, isLoading } = useQuery({
    queryKey: ['admin-catalog-requests', estado],
    queryFn: () => getAdminCatalogRequests({ ...(estado !== 'todas' && { estado }), page_size: 100 }).then(r => r.data),
  })
  function done(message) {
    toast.success(message); setSelected(null); setObservaciones('')
    queryClient.invalidateQueries({ queryKey: ['admin-catalog-requests'] })
    queryClient.invalidateQueries({ queryKey: ['products'] })
    queryClient.invalidateQueries({ queryKey: ['admin-products'] })
  }
  const approve = useMutation({ mutationFn: ({ id, note }) => approveCatalogRequest(id, note), onSuccess: () => done('Solicitud aprobada y publicada.'), onError: err => toast.error(err?.response?.data?.detail || 'No se pudo aprobar.') })
  const reject = useMutation({ mutationFn: ({ id, note }) => rejectCatalogRequest(id, note), onSuccess: () => done('Solicitud rechazada.'), onError: err => toast.error(err?.response?.data?.detail || 'No se pudo rechazar.') })
  const rows = data?.items || []
  return <div className="space-y-4">
    <div className="flex items-center justify-between"><p className="text-sm text-[var(--color-text-secondary)]">Revisa productos y ofertas antes de publicarlos.</p><Select value={estado} onValueChange={setEstado}><SelectTrigger className="w-44"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="pendiente">Pendientes</SelectItem><SelectItem value="aprobada">Aprobadas</SelectItem><SelectItem value="rechazada">Rechazadas</SelectItem><SelectItem value="cancelada">Canceladas</SelectItem><SelectItem value="todas">Todas</SelectItem></SelectContent></Select></div>
    <div className="space-y-2">{isLoading ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20" />) : rows.length === 0 ? <div className="py-16 text-center text-sm text-[var(--color-text-muted)]">No hay solicitudes con este estado.</div> : rows.map(row => <div key={row.id} className="flex items-center gap-4 p-4 border border-[var(--color-border)] rounded-[var(--radius-lg)] bg-[var(--color-surface)]"><div className="flex-1"><div className="flex gap-2 items-center"><span className="font-mono text-xs">#{row.id}</span><Badge variant={STATUS[row.estado]}>{row.estado}</Badge><Badge variant="secondary">{row.tipo === 'producto_nuevo' ? 'Producto nuevo' : 'Oferta existente'}</Badge></div><p className="font-display font-semibold mt-1">{row.nombre || row.producto_nombre}</p><p className="text-xs text-[var(--color-text-muted)]">{row.vendedor_nombre} · {formatQ(row.precio_propuesto)} · {row.stock_propuesto} unidades · {formatDate(row.fecha_creacion)}</p></div><Button size="sm" variant="secondary" onClick={() => { setSelected(row); setObservaciones(row.observaciones_admin || '') }}><Eye size={13} />Revisar</Button></div>)}</div>
    <Dialog open={!!selected} onOpenChange={open => !open && setSelected(null)}><DialogContent className="max-w-2xl"><DialogTitle>Solicitud #{selected?.id}</DialogTitle><DialogDescription>{selected?.tipo === 'producto_nuevo' ? 'Propuesta de producto con oferta inicial' : 'Nueva oferta para un producto existente'}</DialogDescription>{selected && <div className="space-y-4 text-sm"><div className="grid grid-cols-2 gap-3 p-3 rounded bg-[var(--color-background)]"><div><span className="text-xs text-[var(--color-text-muted)]">Vendedor</span><p className="font-semibold">{selected.vendedor_nombre}</p></div><div><span className="text-xs text-[var(--color-text-muted)]">Producto</span><p className="font-semibold">{selected.nombre || selected.producto_nombre}</p></div><div><span className="text-xs text-[var(--color-text-muted)]">Precio</span><p className="font-mono">{formatQ(selected.precio_propuesto)}</p></div><div><span className="text-xs text-[var(--color-text-muted)]">Stock</span><p className="font-mono">{selected.stock_propuesto}</p></div><div><span className="text-xs text-[var(--color-text-muted)]">SKU</span><p className="font-mono">Automático al aprobar</p></div><div><span className="text-xs text-[var(--color-text-muted)]">Categorías</span><p>{selected.categorias.map(c => c.nombre).join(', ') || 'Las del producto'}</p></div></div>{selected.descripcion && <div><Label>Descripción</Label><p className="text-[var(--color-text-secondary)]">{selected.descripcion}</p></div>}{selected.observaciones_vendedor && <div><Label>Comentario del vendedor</Label><p className="p-2 bg-[var(--color-background)] rounded">{selected.observaciones_vendedor}</p></div>}{selected.imagenes.length > 0 && <div><Label>Imágenes</Label><div className="grid grid-cols-4 gap-2 mt-2">{selected.imagenes.map(image => <img key={image.id} src={image.url} alt="Imagen propuesta" className="aspect-square w-full object-cover rounded border" />)}</div></div>}<div><Label>Observaciones del administrador {selected.estado === 'pendiente' && '(obligatorias al rechazar)'}</Label><textarea rows={3} value={observaciones} onChange={e => setObservaciones(e.target.value)} disabled={selected.estado !== 'pendiente'} className="w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2" /></div>{selected.estado === 'pendiente' && <div className="flex justify-end gap-2"><Button variant="danger" onClick={() => { if (!observaciones.trim()) return toast.error('Indica el motivo del rechazo.'); reject.mutate({ id: selected.id, note: observaciones }) }} loading={reject.isPending}><X size={14} />Rechazar</Button><Button onClick={() => approve.mutate({ id: selected.id, note: observaciones })} loading={approve.isPending}><Check size={14} />Aprobar y publicar</Button></div>}</div>}</DialogContent></Dialog>
  </div>
}
