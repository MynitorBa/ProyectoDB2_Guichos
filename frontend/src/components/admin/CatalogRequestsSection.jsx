import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { requestType } from '../../pages/CatalogRequestPage'
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

// Sección de solicitudes de catálogo para el admin: lista por estado y permite aprobar o rechazar con observaciones
export function AdminCatalogRequestsSection() {
  const navigate = useNavigate()
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
    <div className="space-y-2">{isLoading ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20" />) : rows.length === 0 ? <div className="py-16 text-center text-sm text-[var(--color-text-muted)]">No hay solicitudes con este estado.</div> : rows.map(row => <div key={row.id} className="flex items-center gap-4 p-4 border border-[var(--color-border)] rounded-[var(--radius-lg)] bg-[var(--color-surface)]"><div className="flex-1"><div className="flex gap-2 items-center"><span className="font-mono text-xs">#{row.id}</span><Badge variant={STATUS[row.estado]}>{row.estado}</Badge><Badge variant="secondary">{requestType(row.tipo)}</Badge></div><p className="font-display font-semibold mt-1">{row.nombre || row.producto_nombre}</p><p className="text-xs text-[var(--color-text-muted)]">{row.vendedor_nombre} · {formatQ(row.precio_propuesto)} · {row.stock_propuesto} unidades · {formatDate(row.fecha_creacion)}</p></div><Button size="sm" variant="secondary" onClick={() => navigate('/admin/requests/'+row.id)}><Eye size={13} />Revisar</Button></div>)}</div>

  </div>
}
