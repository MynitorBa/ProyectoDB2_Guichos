import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Package, ChevronRight, FileDown } from 'lucide-react'
import { toast } from 'sonner'
import { getOrders, getOrderInvoice } from '../api/orders'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Skeleton } from '../components/ui/skeleton'
import { formatQ, formatDate } from '../lib/utils'

const ESTADO_BADGE = {
  pendiente:       'warning',
  confirmado:      'action',
  en_preparacion:  'action',
  enviado:         'jade',
  entregado:       'success',
  cancelado:       'error',
  reembolsado:     'default',
}

const ESTADO_LABEL = {
  pendiente:       'Pendiente',
  confirmado:      'Confirmado',
  en_preparacion:  'En preparación',
  enviado:         'Enviado',
  entregado:       'Entregado',
  cancelado:       'Cancelado',
  reembolsado:     'Reembolsado',
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export default function OrdersPage() {
  const [downloadingId, setDownloadingId] = useState(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['orders'],
    queryFn: () => getOrders().then((r) => r.data),
  })

  const pedidos = Array.isArray(data) ? data : []

  async function handleDownload(e, pedidoId) {
    e.preventDefault()
    e.stopPropagation()
    setDownloadingId(pedidoId)
    try {
      const res = await getOrderInvoice(pedidoId)
      downloadBlob(res.data, `factura-TiendaYa-${String(pedidoId).padStart(6, '0')}.pdf`)
      toast.success('Factura descargada correctamente.')
    } catch {
      toast.error('No se pudo descargar la factura.')
    } finally {
      setDownloadingId(null)
    }
  }

  if (isLoading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-8 space-y-4">
        <Skeleton className="h-8 w-40" />
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center">
        <p className="font-sans text-sm text-[var(--color-error)]">
          Error al cargar los pedidos. Recarga la página.
        </p>
      </div>
    )
  }

  if (pedidos.length === 0) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center text-center px-4">
        <Package size={64} className="text-[var(--color-border-strong)] mb-4" />
        <h2 className="font-display font-bold text-2xl text-[var(--color-text-primary)] mb-2">
          Sin pedidos todavía
        </h2>
        <p className="font-sans text-sm text-[var(--color-text-secondary)] mb-8 max-w-xs">
          Cuando realices tu primera compra aparecerá aquí.
        </p>
        <Button size="lg" asChild>
          <Link to="/catalog">Ir al catálogo</Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <div className="max-w-3xl mx-auto px-4 py-8">
        <h1 className="font-display font-bold text-2xl text-[var(--color-text-primary)] mb-6">
          Mis pedidos
        </h1>

        <div className="space-y-3">
          {pedidos.map((pedido) => (
            <Link
              key={pedido.id}
              to={`/orders/${pedido.id}`}
              className="flex items-center gap-4 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-4 hover:border-[var(--color-border-strong)] hover:shadow-[var(--shadow-md)] transition-all duration-200"
            >
              <div className="h-10 w-10 rounded-full bg-[var(--color-action)]/10 flex items-center justify-center shrink-0">
                <Package size={18} className="text-[var(--color-action)]" />
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-display font-semibold text-sm text-[var(--color-text-primary)]">
                    Pedido #{pedido.id}
                  </span>
                  <Badge variant={ESTADO_BADGE[pedido.estado] || 'default'}>
                    {ESTADO_LABEL[pedido.estado] || pedido.estado}
                  </Badge>
                </div>
                <p className="font-sans text-xs text-[var(--color-text-muted)] mt-0.5">
                  {formatDate(pedido.fecha || pedido.created_at)}
                </p>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <span className="font-mono font-bold text-base text-[var(--color-text-primary)]">
                  {formatQ(pedido.total)}
                </span>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={(e) => handleDownload(e, pedido.id)}
                  loading={downloadingId === pedido.id}
                  title="Descargar factura PDF"
                >
                  <FileDown size={14} />
                </Button>
                <ChevronRight size={16} className="text-[var(--color-text-muted)]" />
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
