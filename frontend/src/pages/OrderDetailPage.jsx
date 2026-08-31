import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Package, Check } from 'lucide-react'
import { getOrder } from '../api/orders'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Separator } from '../components/ui/separator'
import { Skeleton } from '../components/ui/skeleton'
import { formatQ, formatDatetime } from '../lib/utils'
import { cn } from '../lib/utils'

const ESTADO_BADGE = {
  pendiente: 'warning',
  confirmado: 'action',
  preparando: 'action',
  enviado: 'jade',
  entregado: 'success',
  cancelado: 'error',
  reembolsado: 'default',
}

const PROGRESS_STEPS = [
  { key: 'confirmado', label: 'Confirmado' },
  { key: 'enviado', label: 'Enviado' },
  { key: 'entregado', label: 'Entregado' },
]

// Barra visual del progreso del pedido: Confirmado → Enviado → Entregado; muestra badge si fue cancelado/reembolsado
function ProgressBar({ estado }) {
  const currentIdx = PROGRESS_STEPS.findIndex((s) => s.key === estado)
  const isCancelled = estado === 'cancelado' || estado === 'reembolsado'

  if (isCancelled) {
    return (
      <div className="flex items-center gap-2 px-1 py-3">
        <Badge variant="error" className="text-sm">
          {estado === 'cancelado' ? 'Cancelado' : 'Reembolsado'}
        </Badge>
      </div>
    )
  }

  return (
    <div className="flex items-start gap-0 overflow-x-auto pb-2">
      {PROGRESS_STEPS.map((step, idx) => {
        const done = currentIdx >= idx
        const active = currentIdx === idx
        return (
          <div key={step.key} className="flex items-center flex-1 min-w-[80px]">
            <div className="flex flex-col items-center gap-1.5 flex-1">
              <div
                className={cn(
                  'h-8 w-8 rounded-full border-2 flex items-center justify-center text-xs font-mono font-bold transition-colors',
                  done
                    ? 'bg-[var(--color-success)] border-[var(--color-success)] text-white'
                    : 'bg-[var(--color-surface)] border-[var(--color-border)] text-[var(--color-text-muted)]'
                )}
              >
                {done ? <Check size={14} /> : idx + 1}
              </div>
              <span
                className={cn(
                  'text-[10px] font-sans text-center leading-tight',
                  active
                    ? 'font-semibold text-[var(--color-success)]'
                    : done
                    ? 'text-[var(--color-success)]'
                    : 'text-[var(--color-text-muted)]'
                )}
              >
                {step.label}
              </span>
            </div>
            {idx < PROGRESS_STEPS.length - 1 && (
              <div
                className={cn(
                  'h-0.5 flex-1 mx-1 mb-5 transition-colors',
                  currentIdx > idx ? 'bg-[var(--color-success)]' : 'bg-[var(--color-border)]'
                )}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

// Detalle de un pedido: barra de progreso del envío, líneas de productos y resumen de pago
export default function OrderDetailPage() {
  const { id } = useParams()

  const { data: pedido, isLoading, isError } = useQuery({
    queryKey: ['order', id],
    queryFn: () => getOrder(id).then((r) => r.data),
  })

  if (isLoading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-8 space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-28 w-full" />
      </div>
    )
  }

  if (isError || !pedido) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center">
        <Package size={48} className="mx-auto mb-4 text-[var(--color-border-strong)]" />
        <p className="font-sans text-sm text-[var(--color-text-secondary)]">
          No se pudo cargar el pedido.
        </p>
        <Button variant="secondary" className="mt-4" asChild>
          <Link to="/orders">
            <ArrowLeft size={14} /> Mis pedidos
          </Link>
        </Button>
      </div>
    )
  }

  const lineas = pedido.lineas || []
  const total = pedido.total ?? lineas.reduce((acc, l) => acc + (l.subtotal ?? l.precio_unitario * l.cantidad), 0)
  const subtotal = pedido.subtotal ?? total / 1.12
  const iva = pedido.impuestos ?? total - subtotal

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <div className="max-w-3xl mx-auto px-4 py-8">
        <Button variant="ghost" size="sm" className="mb-5 -ml-2" asChild>
          <Link to="/orders">
            <ArrowLeft size={14} /> Mis pedidos
          </Link>
        </Button>

        <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden shadow-[var(--shadow-sm)]">
          <div className="px-5 py-4 border-b border-[var(--color-border)] flex items-start justify-between flex-wrap gap-3">
            <div>
              <h1 className="font-display font-bold text-xl text-[var(--color-text-primary)]">
                Pedido #{pedido.id}
              </h1>
              <p className="font-sans text-xs text-[var(--color-text-muted)] mt-0.5">
                {formatDatetime(pedido.fecha || pedido.created_at)}
              </p>
            </div>
            <Badge variant={ESTADO_BADGE[pedido.estado] || 'default'} className="text-sm px-3 py-1">
              {pedido.estado}
            </Badge>
          </div>

          <div className="px-5 py-4 border-b border-[var(--color-border)]">
            <h2 className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
              Estado del envío
            </h2>
            <ProgressBar estado={pedido.estado} />
          </div>

          {lineas.length > 0 && (
            <div className="px-5 py-4 border-b border-[var(--color-border)]">
              <h2 className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
                Productos
              </h2>
              <div className="space-y-3">
                {lineas.map((linea, idx) => (
                  <div
                    key={idx}
                    className="flex items-start justify-between gap-4 py-2 border-b border-[var(--color-border)] last:border-0"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="font-display font-semibold text-sm text-[var(--color-text-primary)] line-clamp-2">
                        {linea.producto_nombre}
                      </p>
                      <p className="font-sans text-xs text-[var(--color-text-muted)] mt-0.5">
                        {formatQ(linea.precio_unitario)} × {linea.cantidad}
                      </p>
                    </div>
                    <span className="font-mono font-semibold text-sm text-[var(--color-text-primary)] shrink-0">
                      {formatQ(linea.subtotal ?? linea.precio_unitario * linea.cantidad)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="px-5 py-4">
            <div className="space-y-2">
              <div className="flex justify-between font-sans text-sm text-[var(--color-text-secondary)]">
                <span>Subtotal</span>
                <span className="font-mono">{formatQ(subtotal)}</span>
              </div>
              <div className="flex justify-between font-sans text-sm text-[var(--color-text-secondary)]">
                <span>IVA (12%)</span>
                <span className="font-mono">{formatQ(iva)}</span>
              </div>
              <Separator />
              <div className="flex justify-between font-display font-bold text-base text-[var(--color-text-primary)]">
                <span>Total</span>
                <span className="font-mono">{formatQ(total)}</span>
              </div>
            </div>

            {pedido.pagos?.length > 0 && (
              <div className="mt-4 pt-4 border-t border-[var(--color-border)]">
                <h2 className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-2">
                  Información de pago
                </h2>
                {pedido.pagos.map((pago, idx) => (
                  <div key={idx} className="flex items-center justify-between font-sans text-sm text-[var(--color-text-secondary)]">
                    <span>
                      {pago.estado}
                      {pago.referencia && (
                        <span className="font-mono ml-2 text-xs text-[var(--color-text-muted)]">
                          Ref: {pago.referencia}
                        </span>
                      )}
                    </span>
                    <span className="font-mono">{formatQ(pago.monto)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
