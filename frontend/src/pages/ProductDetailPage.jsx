import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ShoppingCart, Truck, ArrowLeft, Minus, Plus, Star, PackageSearch, Store } from 'lucide-react'
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

// Detalle de producto: galería, selector de oferta (cuando hay varios vendedores), cantidad, atributos por categoría y reseñas
export default function ProductDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { add, loading: cartLoading } = useCart()
  const { user } = useAuth()
  const [selectedImg, setSelectedImg] = useState(0)
  const [cantidad, setCantidad] = useState(1)
  const [selectedOfferId, setSelectedOfferId] = useState(null)
  const [selectedColor, setSelectedColor] = useState(null)
  const [selectedTalla, setSelectedTalla] = useState(null)

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
    if (!selectedOffer?.oferta_id && !product.oferta_id) {
      toast.error('Producto no disponible para compra')
      return
    }
    if (hasVariants && (!selectedColor || !selectedTalla)) {
      toast.error('Selecciona color y talla antes de agregar al carrito')
      return
    }
    try {
      await add(selectedOffer?.oferta_id || product.oferta_id, cantidad)
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
  const imgSrc = (typeof imagenes[selectedImg] === 'string' ? imagenes[selectedImg] : imagenes[selectedImg]?.url) || null
  const resenas = product.resumen_resenas || {}
  const atributos = product.atributos || {}
  const ofertas = product.ofertas || []

  const hasVariants = ofertas.some((o) => o.variante_color || o.variante_talla)
  const uniqueColors = hasVariants ? [...new Set(ofertas.map((o) => o.variante_color).filter(Boolean))] : []
  const uniqueTallas = hasVariants ? [...new Set(ofertas.map((o) => o.variante_talla).filter(Boolean))] : []
  const tallasForColor = selectedColor
    ? [...new Set(ofertas.filter((o) => o.variante_color === selectedColor).map((o) => o.variante_talla).filter(Boolean))]
    : uniqueTallas
  const variantOffer = hasVariants
    ? ofertas.find((o) => o.variante_color === selectedColor && o.variante_talla === selectedTalla)
      || (selectedColor ? ofertas.find((o) => o.variante_color === selectedColor) : null)
    : null

  const selectedOffer = hasVariants
    ? (variantOffer || ofertas[0])
    : (ofertas.find((item) => item.oferta_id === selectedOfferId) || ofertas[0])
  const displayPrice = selectedOffer?.precio ?? product.precio
  const displayStock = selectedOffer?.stock ?? product.stock ?? 0
  const displayAvailable = selectedOffer?.disponible ?? product.disponible
  const displayVendor = selectedOffer?.vendedor_nombre ?? product.vendedor_nombre

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
                      src={typeof img === 'string' ? img : img?.url}
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
              {(product.categorias || (product.categoria ? [product.categoria] : [])).map(cat => (
                <Badge key={cat.slug} variant="jade">{cat.nombre}</Badge>
              ))}
              {displayAvailable ? (
                <Badge variant="success">{displayStock > 0 ? `${displayStock} en stock` : 'En stock'}</Badge>
              ) : (
                <Badge variant="error">Sin stock</Badge>
              )}
              {displayAvailable && displayStock > 0 && displayStock <= 5 && (
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
                {formatQ(displayPrice)}
              </span>
              {product.moneda && (
                <span className="font-sans text-sm text-[var(--color-text-muted)] mb-1">
                  {product.moneda}
                </span>
              )}
            </div>

            {displayVendor && (
              <div className="flex items-center gap-2.5 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2.5 w-fit">
                <Store size={15} className="text-[var(--color-action)] shrink-0" strokeWidth={1.5} />
                <div>
                  <p className="font-sans text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] leading-none mb-0.5">Vendedor</p>
                  <p className="font-display font-semibold text-sm text-[var(--color-text-primary)]">
                    {displayVendor}
                  </p>
                </div>
              </div>
            )}

            {hasVariants && uniqueColors.length > 0 && (
              <div className="space-y-2">
                <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Color</p>
                <div className="flex flex-wrap gap-2">
                  {uniqueColors.map((color) => {
                    const available = ofertas.some((o) => o.variante_color === color && o.disponible)
                    return (
                      <button
                        key={color}
                        type="button"
                        onClick={() => { setSelectedColor(color); setSelectedTalla(null); setCantidad(1) }}
                        disabled={!available}
                        className={`px-3 py-1.5 rounded-full border text-sm font-sans transition-colors ${
                          selectedColor === color
                            ? 'border-[var(--color-action)] bg-[var(--color-action)]/10 text-[var(--color-action)] font-semibold'
                            : available
                              ? 'border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-primary)] hover:border-[var(--color-action)]'
                              : 'border-[var(--color-border)] bg-[var(--color-background)] text-[var(--color-text-muted)] line-through cursor-not-allowed'
                        }`}
                      >
                        {color}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {hasVariants && uniqueTallas.length > 0 && (
              <div className="space-y-2">
                <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Talla</p>
                <div className="flex flex-wrap gap-2">
                  {tallasForColor.map((talla) => {
                    const available = ofertas.some(
                      (o) => o.variante_talla === talla && (!selectedColor || o.variante_color === selectedColor) && o.disponible
                    )
                    return (
                      <button
                        key={talla}
                        type="button"
                        onClick={() => { setSelectedTalla(talla); setCantidad(1) }}
                        disabled={!available}
                        className={`min-w-[40px] px-3 py-1.5 rounded-[var(--radius-md)] border text-sm font-mono font-semibold transition-colors ${
                          selectedTalla === talla
                            ? 'border-[var(--color-action)] bg-[var(--color-action)] text-white'
                            : available
                              ? 'border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-primary)] hover:border-[var(--color-action)]'
                              : 'border-[var(--color-border)] bg-[var(--color-background)] text-[var(--color-text-muted)] line-through cursor-not-allowed'
                        }`}
                      >
                        {talla}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {!hasVariants && ofertas.length > 1 && (
              <div className="space-y-2">
                <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                  Otras ofertas
                </p>
                {ofertas.map((offer) => (
                  <button
                    key={offer.oferta_id}
                    type="button"
                    onClick={() => { setSelectedOfferId(offer.oferta_id); setCantidad(1) }}
                    className={`w-full flex items-center justify-between rounded-[var(--radius-md)] border px-3 py-2 text-left ${
                      selectedOffer?.oferta_id === offer.oferta_id
                        ? 'border-[var(--color-action)] bg-[var(--color-action)]/5'
                        : 'border-[var(--color-border)] bg-[var(--color-surface)]'
                    }`}
                  >
                    <span className="font-sans text-sm">{offer.vendedor_nombre}</span>
                    <span className="font-mono text-sm font-bold">{formatQ(offer.precio)} · {offer.stock} disponibles</span>
                  </button>
                ))}
              </div>
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
                  onClick={() => setCantidad((c) => Math.min(displayStock || 1, c + 1))}
                  className="h-full px-3 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-border)] transition-colors rounded-r-[var(--radius-md)]"
                >
                  <Plus size={14} />
                </button>
              </div>

              <Button
                size="lg"
                className="flex-1"
                disabled={!displayAvailable}
                loading={cartLoading}
                onClick={handleAdd}
              >
                <ShoppingCart size={18} />
                {displayAvailable ? 'Agregar al carrito' : 'Sin stock'}
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

      {displayAvailable && (
        <div className="fixed bottom-0 left-0 right-0 z-40 lg:hidden bg-[var(--color-surface)] border-t border-[var(--color-border)] shadow-[var(--shadow-xl)] px-4 py-3 flex items-center gap-3">
          <div className="flex-1">
            <p className="font-display font-bold text-lg text-[var(--color-text-primary)]">
              {formatQ(displayPrice)}
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
