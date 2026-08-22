import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ShoppingCart, Truck, ArrowLeft, Minus, Plus, Star, PackageSearch } from 'lucide-react'
import { toast } from 'sonner'
import { getProduct } from '../api/products'
import { useCart } from '../context/CartContext'
import { useAuth } from '../context/AuthContext'
import { ProductImage } from '../components/product/ProductImage'
import { CategoryAttrPanel } from '../components/product/CategoryAttrPanel'
import { StarRating } from '../components/ui/star-rating'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Skeleton } from '../components/ui/skeleton'
import { Separator } from '../components/ui/separator'
import { formatQ } from '../lib/utils'

function DetailSkeleton() {
  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
        <div className="space-y-3">
          <Skeleton className="aspect-square w-full rounded-[var(--radius-xl)]" />
          <div className="grid grid-cols-4 gap-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="aspect-square rounded-[var(--radius-md)]" />
            ))}
          </div>
        </div>
        <div className="space-y-4">
          <Skeleton className="h-5 w-24" />
          <Skeleton className="h-9 w-3/4" />
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-10 w-40" />
          <Skeleton className="h-24 w-full rounded-[var(--radius-lg)]" />
          <Skeleton className="h-12 w-full rounded-[var(--radius-md)]" />
        </div>
      </div>
    </div>
  )
}

export default function ProductDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { add, loading: cartLoading } = useCart()
  const { user } = useAuth()
  const [selectedImg, setSelectedImg] = useState(0)
  const [cantidad, setCantidad] = useState(1)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['product', id],
    queryFn: () => getProduct(id).then((r) => r.data),
  })

  const product = data

  async function handleAdd() {
    if (!user) {
      toast.error('Inicia sesión para agregar al carrito')
      navigate('/login')
      return
    }
    if (!product.mysql_id) {
      toast.error('Producto no disponible para compra')
      return
    }
    try {
      await add(product.mysql_id, cantidad)
      toast.success(`${product.nombre} agregado al carrito`)
    } catch {
      toast.error('No se pudo agregar al carrito')
    }
  }

  if (isLoading) return <DetailSkeleton />

  if (isError || !product) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-16 text-center">
        <PackageSearch size={56} className="text-[var(--color-border-strong)] mb-4 mx-auto" strokeWidth={1.5} />
        <h2 className="font-display font-bold text-2xl text-[var(--color-text-primary)] mb-2">
          Producto no encontrado
        </h2>
        <p className="font-sans text-sm text-[var(--color-text-secondary)] mb-6">
          El producto que buscas no existe o fue removido.
        </p>
        <Button variant="secondary" onClick={() => navigate(-1)}>
          <ArrowLeft size={14} /> Volver
        </Button>
      </div>
    )
  }

  const imagenes = product.imagenes || []
  const imgSrc = imagenes[selectedImg]?.url || null
  const resenas = product.resumen_resenas || {}
  const atributos = product.atributos || {}

  const starCounts = [5, 4, 3, 2, 1].map((n) => ({
    stars: n,
    count: Math.round((resenas.total || 0) * (n === Math.round(resenas.promedio) ? 0.5 : 0.1)),
  }))

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <div className="max-w-6xl mx-auto px-4 py-6">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 text-sm font-sans text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors mb-6"
        >
          <ArrowLeft size={14} /> Volver al catálogo
        </button>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
          <div className="space-y-3">
            <div className="rounded-[var(--radius-xl)] overflow-hidden border border-[var(--color-border)] bg-[var(--color-surface)]">
              <ProductImage
                src={imgSrc}
                alt={product.nombre}
                categoria={product.categoria}
                nombre={product.nombre}
                aspectRatio="aspect-square"
                size="lg"
              />
            </div>
            {imagenes.length > 1 && (
              <div className="grid grid-cols-5 gap-2">
                {imagenes.map((img, idx) => (
                  <button
                    key={idx}
                    onClick={() => setSelectedImg(idx)}
                    className={`rounded-[var(--radius-md)] overflow-hidden border-2 transition-colors aspect-square ${
                      selectedImg === idx
                        ? 'border-[var(--color-action)]'
                        : 'border-[var(--color-border)] hover:border-[var(--color-border-strong)]'
                    }`}
                  >
                    <ProductImage
                      src={img.url}
                      alt={`${product.nombre} - imagen ${idx + 1}`}
                      categoria={product.categoria}
                      nombre={product.nombre}
                      aspectRatio="aspect-square"
                      size="sm"
                    />
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="space-y-5">
            <div className="flex items-center gap-2 flex-wrap">
              {product.categoria?.nombre && (
                <Badge variant="jade">{product.categoria.nombre}</Badge>
              )}
              {product.disponible ? (
                <Badge variant="success">{product.stock > 0 ? `${product.stock} en stock` : 'En stock'}</Badge>
              ) : (
                <Badge variant="error">Sin stock</Badge>
              )}
              {product.disponible && product.stock > 0 && product.stock <= 5 && (
                <span className="font-sans text-xs text-[var(--color-error)]">¡Últimas unidades!</span>
              )}
            </div>

            <h1 className="font-display font-bold text-2xl lg:text-3xl text-[var(--color-text-primary)] leading-tight">
              {product.nombre}
            </h1>

            {resenas.total > 0 && (
              <div className="flex items-center gap-3">
                <StarRating value={resenas.promedio} size={16} count={resenas.total} />
              </div>
            )}

            <div className="flex items-end gap-3">
              <span className="font-mono font-bold text-4xl text-[var(--color-text-primary)]">
                {formatQ(product.precio)}
              </span>
              {product.moneda && (
                <span className="font-sans text-sm text-[var(--color-text-muted)] mb-1">
                  {product.moneda}
                </span>
              )}
            </div>

            {product.vendedor_nombre && (
              <p className="font-sans text-sm text-[var(--color-text-secondary)]">
                Vendedor:{' '}
                <span className="font-semibold text-[var(--color-text-primary)]">
                  {product.vendedor_nombre}
                </span>
              </p>
            )}

            <CategoryAttrPanel
              categoria={product.categoria}
              atributos={product.atributos}
            />

            <div className="flex items-center gap-3 pt-1">
              <div className="flex items-center gap-1 border border-[var(--color-border)] rounded-[var(--radius-md)] h-10">
                <button
                  onClick={() => setCantidad((c) => Math.max(1, c - 1))}
                  className="h-full px-3 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-border)] transition-colors rounded-l-[var(--radius-md)]"
                >
                  <Minus size={14} />
                </button>
                <span className="font-mono font-semibold text-base w-10 text-center text-[var(--color-text-primary)]">
                  {cantidad}
                </span>
                <button
                  onClick={() => setCantidad((c) => c + 1)}
                  className="h-full px-3 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-border)] transition-colors rounded-r-[var(--radius-md)]"
                >
                  <Plus size={14} />
                </button>
              </div>

              <Button
                size="lg"
                className="flex-1"
                disabled={!product.disponible}
                loading={cartLoading}
                onClick={handleAdd}
              >
                <ShoppingCart size={18} />
                {product.disponible ? 'Agregar al carrito' : 'Sin stock'}
              </Button>
            </div>

            <div className="flex items-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
              <Truck size={16} className="text-[var(--color-jade)] shrink-0" />
              <p className="font-sans text-sm text-[var(--color-text-secondary)]">
                Envío: <span className="font-semibold text-[var(--color-text-primary)]">Q35–Q75</span> según municipio
              </p>
            </div>
          </div>
        </div>

        <div className="mt-12 space-y-10">
          <Separator />

          <section>
            <h2 className="font-display font-bold text-xl text-[var(--color-text-primary)] mb-4">
              Descripción
            </h2>
            <p className="font-sans text-base text-[var(--color-text-secondary)] leading-relaxed max-w-3xl">
              {product.descripcion || 'Sin descripción disponible.'}
            </p>
          </section>

          <Separator />

          {Object.keys(atributos).length > 0 && (
            <>
              <section>
                <h2 className="font-display font-bold text-xl text-[var(--color-text-primary)] mb-4">
                  Especificaciones técnicas
                </h2>
                <div className="overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-border)]">
                  <table className="w-full text-sm">
                    <tbody>
                      {Object.entries(atributos).map(([key, value], idx) => (
                        <tr
                          key={key}
                          className={idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]'}
                        >
                          <td className="px-5 py-3 font-sans font-semibold text-[var(--color-text-secondary)] w-2/5 capitalize border-b border-[var(--color-border)]">
                            {key.replace(/_/g, ' ')}
                          </td>
                          <td className="px-5 py-3 font-sans text-[var(--color-text-primary)] border-b border-[var(--color-border)]">
                            {typeof value === 'boolean' ? (value ? 'Sí' : 'No') : String(value)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
              <Separator />
            </>
          )}

          <section>
            <h2 className="font-display font-bold text-xl text-[var(--color-text-primary)] mb-6">
              Reseñas de clientes
            </h2>
            {resenas.total > 0 ? (
              <div className="flex flex-col sm:flex-row gap-8">
                <div className="flex flex-col items-center justify-center gap-2 sm:min-w-[160px]">
                  <span className="font-mono font-bold text-6xl text-[var(--color-text-primary)]">
                    {resenas.promedio?.toFixed(1)}
                  </span>
                  <StarRating value={resenas.promedio} size={18} showValue={false} />
                  <span className="font-sans text-sm text-[var(--color-text-muted)]">
                    {resenas.total} reseña{resenas.total !== 1 ? 's' : ''}
                  </span>
                </div>
                <div className="flex-1 space-y-2">
                  {starCounts.map(({ stars, count }) => {
                    const pct = resenas.total ? Math.round((count / resenas.total) * 100) : 0
                    return (
                      <div key={stars} className="flex items-center gap-3">
                        <div className="flex items-center gap-1 w-16 shrink-0">
                          <span className="font-sans text-xs text-[var(--color-text-secondary)]">{stars}</span>
                          <Star size={12} className="fill-amber-400 text-amber-400" />
                        </div>
                        <div className="flex-1 h-2 rounded-full bg-[var(--color-border)] overflow-hidden">
                          <div
                            className="h-full rounded-full bg-amber-400"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="font-sans text-xs text-[var(--color-text-muted)] w-8 text-right">
                          {pct}%
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            ) : (
              <div className="text-center py-10">
                <Star size={36} className="mx-auto mb-3 text-[var(--color-border-strong)]" />
                <p className="font-sans text-sm text-[var(--color-text-muted)]">
                  Este producto aún no tiene reseñas.
                </p>
              </div>
            )}
          </section>
        </div>
      </div>

      {product.disponible && (
        <div className="fixed bottom-0 left-0 right-0 z-40 lg:hidden bg-[var(--color-surface)] border-t border-[var(--color-border)] shadow-[var(--shadow-xl)] px-4 py-3 flex items-center gap-3">
          <div className="flex-1">
            <p className="font-display font-bold text-lg text-[var(--color-text-primary)]">
              {formatQ(product.precio)}
            </p>
            <p className="font-sans text-xs text-[var(--color-text-muted)] line-clamp-1">
              {product.nombre}
            </p>
          </div>
          <Button size="md" loading={cartLoading} onClick={handleAdd}>
            <ShoppingCart size={16} /> Agregar
          </Button>
        </div>
      )}
    </div>
  )
}
