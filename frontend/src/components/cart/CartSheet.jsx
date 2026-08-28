import { Link } from 'react-router-dom'
import { ShoppingCart, Minus, Plus, Trash2, ArrowRight } from 'lucide-react'
import { Sheet, SheetContent } from '../ui/sheet'
import { Button } from '../ui/button'
import { Separator } from '../ui/separator'
import { ProductImage } from '../product/ProductImage'
import { formatQ } from '../../lib/utils'
import { useCart } from '../../context/CartContext'

// Panel lateral deslizante del carrito: lista items, permite eliminarlos y muestra resumen con IVA para ir al checkout
export function CartSheet({ open, onClose }) {
  const { cart, remove, loading } = useCart()
  const items = cart?.items || []
  const subtotal = items.reduce((s, i) => s + (i.precio_unitario * i.cantidad), 0)
  const iva = subtotal * 0.12
  const total = subtotal + iva

  return (
    <Sheet open={open} onOpenChange={onClose}>
      <SheetContent side="right" title={`Carrito (${items.length})`}>
        {items.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 gap-4 px-5">
            <div className="h-16 w-16 rounded-full bg-[var(--color-border)] flex items-center justify-center">
              <ShoppingCart size={28} className="text-[var(--color-text-muted)]" />
            </div>
            <div className="text-center">
              <p className="font-display font-semibold text-[var(--color-text-primary)]">Tu carrito está vacío</p>
              <p className="font-sans text-sm text-[var(--color-text-secondary)] mt-1">Agrega productos desde el catálogo</p>
            </div>
            <Button variant="primary" size="md" asChild onClick={onClose}>
              <Link to="/">Ver productos</Link>
            </Button>
          </div>
        ) : (
          <div className="flex flex-col h-full">
            {/* Items */}
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
              {items.map(item => (
                <div key={item.id} className="flex gap-3">
                  <div className="h-16 w-16 shrink-0 rounded-[var(--radius-md)] overflow-hidden border border-[var(--color-border)]">
                    <ProductImage
                      src={item.imagen_url}
                      categoria={item.categoria_slug}
                      nombre={item.nombre}
                      aspectRatio="aspect-square"
                      size="sm"
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-sans text-sm font-medium text-[var(--color-text-primary)] line-clamp-2 leading-snug">
                      {item.nombre}
                    </p>
                    <p className="font-display font-semibold text-sm text-[var(--color-text-primary)] mt-0.5">
                      {formatQ(item.precio_unitario * item.cantidad)}
                    </p>
                    <div className="flex items-center gap-2 mt-1.5">
                      <span className="font-sans text-xs text-[var(--color-text-muted)]">Cant: {item.cantidad}</span>
                      <button
                        onClick={() => remove(item.id)}
                        disabled={loading}
                        className="ml-auto p-1 rounded text-[var(--color-text-muted)] hover:text-[var(--color-error)] hover:bg-[var(--color-error-light)] transition-colors"
                        aria-label="Eliminar"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Resumen */}
            <div className="border-t border-[var(--color-border)] px-5 py-4 space-y-3 bg-[var(--color-background)]">
              <div className="space-y-1.5">
                <div className="flex justify-between font-sans text-sm">
                  <span className="text-[var(--color-text-secondary)]">Subtotal</span>
                  <span className="text-[var(--color-text-primary)]">{formatQ(subtotal)}</span>
                </div>
                <div className="flex justify-between font-sans text-sm">
                  <span className="text-[var(--color-text-secondary)]">IVA (12%)</span>
                  <span className="text-[var(--color-text-primary)]">{formatQ(iva)}</span>
                </div>
                <Separator />
                <div className="flex justify-between font-display font-bold text-base">
                  <span>Total</span>
                  <span>{formatQ(total)}</span>
                </div>
              </div>
              <Button variant="primary" size="lg" className="w-full" asChild onClick={onClose}>
                <Link to="/checkout">
                  Ir al pago <ArrowRight size={16} />
                </Link>
              </Button>
              <Button variant="ghost" size="md" className="w-full" asChild onClick={onClose}>
                <Link to="/cart">Ver carrito completo</Link>
              </Button>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}
