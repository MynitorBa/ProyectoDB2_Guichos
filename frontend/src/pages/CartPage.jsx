import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Trash2, ShoppingBag, ArrowRight } from 'lucide-react'
import { useCart } from '../context/CartContext'
import { Button } from '../components/ui/button'
import { Separator } from '../components/ui/separator'
import { Skeleton } from '../components/ui/skeleton'
import { formatQ } from '../lib/utils'

const IVA_RATE = 0.12

// Página de carrito: lista items con opción de eliminar y muestra resumen con subtotal, IVA (12%) y total
export default function CartPage() {
  const { cart, loading, fetchCart, remove } = useCart()
  const navigate = useNavigate()

  useEffect(() => {
    fetchCart()
  }, [fetchCart])

  const items = cart?.items || []
  const subtotal = items.reduce((acc, item) => acc + (item.subtotal || item.precio * item.cantidad || 0), 0)
  const iva = subtotal * IVA_RATE
  const total = subtotal + iva

  if (loading && items.length === 0) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-8">
        <h1 className="font-display font-bold text-2xl text-[var(--color-text-primary)] mb-6">Mi carrito</h1>
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center text-center px-4">
        <ShoppingBag size={64} className="text-[var(--color-border-strong)] mb-4" />
        <h2 className="font-display font-bold text-2xl text-[var(--color-text-primary)] mb-2">
          Tu carrito está vacío
        </h2>
        <p className="font-sans text-sm text-[var(--color-text-secondary)] mb-8 max-w-xs">
          Explora nuestros productos y agrega los que te interesen.
        </p>
        <Button size="lg" asChild>
          <Link to="/catalog">Ver catálogo</Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <div className="max-w-5xl mx-auto px-4 py-8">
        <h1 className="font-display font-bold text-2xl text-[var(--color-text-primary)] mb-6">
          Mi carrito{' '}
          <span className="font-sans font-normal text-base text-[var(--color-text-muted)]">
            ({items.length} {items.length === 1 ? 'artículo' : 'artículos'})
          </span>
        </h1>

        <div className="flex flex-col lg:flex-row gap-6">
          <div className="flex-1 space-y-3">
            {items.map((item) => (
              <div
                key={item.id}
                className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-4 flex items-center gap-4"
              >
                <div className="h-20 w-20 shrink-0 rounded-[var(--radius-md)] overflow-hidden bg-[var(--color-background)] border border-[var(--color-border)] flex items-center justify-center">
                  {item.imagen_url ? (
                    <img
                      src={item.imagen_url}
                      alt={item.nombre}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <ShoppingBag size={24} className="text-[var(--color-text-muted)]" strokeWidth={1.5} />
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <h3 className="font-display font-semibold text-sm text-[var(--color-text-primary)] line-clamp-2">
                    {item.nombre}
                  </h3>
                  <p className="font-sans text-xs text-[var(--color-text-muted)] mt-0.5">
                    {formatQ(item.precio)} × {item.cantidad}
                  </p>
                </div>

                <div className="text-right shrink-0">
                  <p className="font-mono font-bold text-base text-[var(--color-text-primary)]">
                    {formatQ(item.subtotal ?? item.precio * item.cantidad)}
                  </p>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="mt-1 text-[var(--color-error)] hover:text-[var(--color-error)] hover:bg-[var(--color-error)]/10"
                    onClick={() => remove(item.id)}
                    disabled={loading}
                  >
                    <Trash2 size={14} />
                  </Button>
                </div>
              </div>
            ))}
          </div>

          <aside className="lg:w-80 shrink-0">
            <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5 sticky top-20">
              <h2 className="font-display font-semibold text-base text-[var(--color-text-primary)] mb-4">
                Resumen del pedido
              </h2>

              <div className="space-y-3">
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

              <Button
                size="lg"
                className="w-full mt-5"
                onClick={() => navigate('/checkout')}
                disabled={loading}
              >
                Proceder al pago <ArrowRight size={16} />
              </Button>

              <Button
                variant="ghost"
                size="sm"
                className="w-full mt-2"
                asChild
              >
                <Link to="/catalog">Continuar comprando</Link>
              </Button>
            </div>
          </aside>
        </div>
      </div>
    </div>
  )
}
