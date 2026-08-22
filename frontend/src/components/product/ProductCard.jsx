import { Link } from 'react-router-dom'
import { ShoppingCart, CheckCircle } from 'lucide-react'
import { useState } from 'react'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import { StarRating } from '../ui/star-rating'
import { ProductImage } from './ProductImage'
import { formatQ } from '../../lib/utils'
import { useCart } from '../../context/CartContext'
import { useAuth } from '../../context/AuthContext'
import { toast } from 'sonner'

export function ProductCard({ product }) {
  const { add } = useCart()
  const { user } = useAuth()
  const [added, setAdded] = useState(false)
  const [adding, setAdding] = useState(false)

  const imgSrc = product.imagenes?.[0]?.url || null
  const resenas = product.resumen_resenas || {}
  const categoria = product.categoria

  async function handleAdd(e) {
    e.preventDefault()
    if (!user) { toast.error('Inicia sesión para agregar al carrito'); return }
    if (!product.mysql_id) { toast.error('Producto no disponible para compra'); return }
    setAdding(true)
    try {
      await add(product.mysql_id, 1)
      setAdded(true)
      toast.success(`${product.nombre} agregado al carrito`)
      setTimeout(() => setAdded(false), 2000)
    } catch {
      toast.error('No se pudo agregar al carrito')
    } finally {
      setAdding(false)
    }
  }

  return (
    <Link
      to={`/products/${product._id}`}
      className="group flex flex-col bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-md)] hover:border-[var(--color-border-strong)] transition-all duration-200 focus-visible:outline-2 focus-visible:outline-[var(--color-action)]"
    >
      <div className="relative overflow-hidden">
        <ProductImage
          src={imgSrc}
          alt={product.nombre}
          categoria={categoria}
          nombre={product.nombre}
          aspectRatio="aspect-square"
        />
        {!product.disponible && (
          <div className="absolute inset-0 bg-white/70 flex items-center justify-center">
            <Badge variant="default" className="text-xs">Sin stock</Badge>
          </div>
        )}
        {categoria?.nombre && (
          <div className="absolute top-2 left-2">
            <Badge variant="jade">{categoria.nombre}</Badge>
          </div>
        )}
      </div>

      <div className="flex flex-col flex-1 p-3 gap-1.5">
        <p className="font-sans text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider truncate">
          {product.vendedor_nombre}
        </p>
        <h3 className="font-display font-semibold text-sm text-[var(--color-text-primary)] line-clamp-2 leading-snug min-h-[2.5rem]">
          {product.nombre}
        </h3>

        {resenas.total > 0 && (
          <StarRating value={resenas.promedio} size={12} count={resenas.total} />
        )}

        <div className="mt-auto pt-2 flex items-end justify-between gap-2">
          <span className="font-display font-bold text-lg text-[var(--color-text-primary)]">
            {formatQ(product.precio)}
          </span>
        </div>

        {product.stock !== undefined && product.stock !== null && product.disponible && product.stock > 0 && (
          product.stock <= 5
            ? <span className="font-sans text-xs text-[var(--color-error)]">¡Solo {product.stock} en stock!</span>
            : <span className="font-sans text-xs text-[var(--color-text-muted)]">{product.stock} en stock</span>
        )}

        <Button
          variant={added ? 'jade' : 'primary'}
          size="sm"
          className="w-full mt-1"
          loading={adding}
          disabled={!product.disponible}
          onClick={handleAdd}
        >
          {added ? (
            <><CheckCircle size={14} /> Agregado</>
          ) : (
            <><ShoppingCart size={14} /> Agregar</>
          )}
        </Button>
      </div>
    </Link>
  )
}
