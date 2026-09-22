import { useState, useEffect } from 'react'
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ShoppingCart, Truck, ArrowLeft, Minus, Plus, Star, PackageSearch, Store, ShieldCheck, Zap } from 'lucide-react'
import { motion, useInView } from 'motion/react'
import { useRef } from 'react'
import { toast } from 'sonner'
import { getProduct, getActiveFlashSales, reserveFlashSale } from '../api/products'
import { useCart } from '../context/CartContext'
import { useAuth } from '../context/AuthContext'
import { ProductImage } from '../components/product/ProductImage'
import { CategoryAttrPanel } from '../components/product/CategoryAttrPanel'
import ReviewSection from '../components/product/ReviewSection'
import { StarRating } from '../components/ui/star-rating'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Skeleton } from '../components/ui/skeleton'
import { Separator } from '../components/ui/separator'
import { formatQ } from '../lib/utils'

const ease = [0.23, 1, 0.32, 1]

function Reveal({ children, className, delay = 0 }) {
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-30px' })
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 18 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.55, ease, delay }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

function DetailSkeleton() {
  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
        <div className="space-y-3">
          <Skeleton className="aspect-square w-full rounded-2xl" />
          <div className="grid grid-cols-4 gap-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="aspect-square rounded-xl" />
            ))}
          </div>
        </div>
        <div className="space-y-4">
          <Skeleton className="h-5 w-24" />
          <Skeleton className="h-9 w-3/4" />
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-12 w-44" />
          <Skeleton className="h-20 w-full rounded-2xl" />
          <Skeleton className="h-13 w-full rounded-full" />
        </div>
      </div>
    </div>
  )
}

export default function ProductDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const desdeTienda = searchParams.get('desde_tienda')
  const { add, fetchCart, loading: cartLoading } = useCart()
  const { user } = useAuth()
  const [selectedImg, setSelectedImg] = useState(0)
  const [cantidad, setCantidad] = useState(1)
  const [flashCantidad, setFlashCantidad] = useState(1)
  const [selectedOfferId, setSelectedOfferId] = useState(null)
  const [selectedVariantId, setSelectedVariantId] = useState(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['product', id],
    queryFn: () => getProduct(id).then((r) => r.data),
  })
  const { data: allFlashRows = [], refetch: refetchFlash } = useQuery({
    queryKey: ['flash-sales-product', id],
    queryFn: () => getActiveFlashSales().then(r => r.data),
    enabled: Boolean(data),
    refetchInterval: 10_000,
  })
  const allOfferIds = new Set((data?.ofertas || []).map(o => o.oferta_id))
  const flashRows = allFlashRows.filter(f => allOfferIds.has(f.oferta_id))
  const [clock, setClock] = useState(Date.now())
  useEffect(() => {
    const timer = setInterval(() => setClock(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    if (!desdeTienda || !data?.ofertas?.length) return
    const vendorId = parseInt(desdeTienda, 10)
    const vendorOffer = data.ofertas.find(o => o.vendedor_id === vendorId)
    if (vendorOffer) {
      setSelectedOfferId(vendorOffer.oferta_id)
      setSelectedVariantId(vendorOffer.producto_variante_id)
    }
  }, [data, desdeTienda])

  useEffect(() => { setFlashCantidad(1) }, [selectedOfferId])

  const product = data

  async function handleAdd() {
    if (!user) {
      toast.error('Inicia sesión para agregar al carrito')
      navigate('/login')
      return
    }
    if (!selectedOffer?.oferta_id) {
      toast.error('Producto no disponible para compra')
      return
    }
    try {
      await add(selectedOffer.oferta_id, cantidad)
      toast.success(`${product.nombre} agregado al carrito`)
    } catch {
      toast.error('No se pudo agregar al carrito')
    }
  }

  async function handleFlashReserve() {
    if (!user) {
      toast.error('Inicia sesión para reservar la promoción')
      navigate('/login')
      return
    }
    if (!flashSale) return
    try {
      await reserveFlashSale(flashSale.id, flashCantidad)
      await fetchCart()
      await refetchFlash()
      toast.success(`${flashCantidad} unidad${flashCantidad > 1 ? 'es' : ''} flash reservada${flashCantidad > 1 ? 's' : ''} durante cinco minutos.`)
      navigate('/cart')
    } catch (error) {
      toast.error(error.response?.data?.detail || 'No se pudo reservar la unidad flash.')
      refetchFlash()
    }
  }

  if (isLoading) return <DetailSkeleton />

  if (isError || !product) {
    return (
      <motion.div
        className="max-w-6xl mx-auto px-4 py-24 text-center"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease }}
      >
        <div className="h-24 w-24 rounded-full flex items-center justify-center mx-auto mb-5"
          style={{ backgroundColor: 'rgba(41,182,246,0.08)' }}>
          <PackageSearch size={40} className="text-[#29B6F6]" strokeWidth={1.5} />
        </div>
        <h2 className="font-display font-bold text-2xl text-[var(--color-text-primary)] mb-2">
          Producto no encontrado
        </h2>
        <p className="font-sans text-sm text-[var(--color-text-secondary)] mb-6">
          El producto que buscas no existe o fue removido.
        </p>
        <button
          onClick={() => navigate(-1)}
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full font-sans font-semibold text-sm text-white transition-opacity hover:opacity-88"
          style={{ background: 'linear-gradient(135deg, #29B6F6, #0288D1)' }}
        >
          <ArrowLeft size={14} /> Volver
        </button>
      </motion.div>
    )
  }

  const imagenes = product.imagenes || []
  const imgSrc = (typeof imagenes[selectedImg] === 'string' ? imagenes[selectedImg] : imagenes[selectedImg]?.url) || null
  const resenas = product.resumen_resenas || {}

  const rawOfertas = product.ofertas || []
  const flashByOfferId = Object.fromEntries(flashRows.map(f => [f.oferta_id, f]))
  const sortedOfertas = [...rawOfertas].sort((a, b) => {
    if (a.es_tiendaya !== b.es_tiendaya) return (b.es_tiendaya ? 1 : 0) - (a.es_tiendaya ? 1 : 0)
    const aFlash = Boolean(flashByOfferId[a.oferta_id])
    const bFlash = Boolean(flashByOfferId[b.oferta_id])
    if (aFlash !== bFlash) return (bFlash ? 1 : 0) - (aFlash ? 1 : 0)
    return a.precio - b.precio
  })
  const variantMap = new Map()
  sortedOfertas.forEach(offer => {
    const vid = offer.producto_variante_id
    if (!variantMap.has(vid)) {
      variantMap.set(vid, { variante_id: vid, atributos: offer.variante_atributos || {}, ofertas: [] })
    }
    variantMap.get(vid).ofertas.push(offer)
  })
  const variantesAgrupadas = Array.from(variantMap.values())
  const mostrarSelector = variantesAgrupadas.length >= 2
  const unicaClave = mostrarSelector &&
    variantesAgrupadas.every(v => {
      const keys = Object.keys(v.atributos)
      return keys.length === 1 && keys[0] === Object.keys(variantesAgrupadas[0].atributos)[0]
    })
      ? Object.keys(variantesAgrupadas[0].atributos)[0]
      : null

  const selectedVariant = variantesAgrupadas.find(v => v.variante_id === selectedVariantId) ?? variantesAgrupadas[0]
  const ofertasVariante = selectedVariant?.ofertas ?? rawOfertas
  const selectedOffer = ofertasVariante.find(o => o.oferta_id === selectedOfferId) ?? ofertasVariante[0]
  const flashSale = flashRows.find(row => row.oferta_id === selectedOffer?.oferta_id)
  const atributos = { ...(product.atributos || {}), ...(selectedVariant?.atributos || {}) }
  const displayPrice = flashSale?.precio_promocional ?? selectedOffer?.precio ?? product.precio
  const displayStock = (selectedOffer?.stock ?? 0) + (flashSale ? (flashSale.unidades_disponibles ?? 0) : 0)
  const displayAvailable = selectedOffer != null
    ? ((selectedOffer.disponible ?? false) || (selectedOffer.stock ?? 0) > 0)
    : (product.disponible ?? false)
  const displayVendor = selectedOffer?.vendedor_nombre ?? null
  const displayVendorId = selectedOffer?.vendedor_id ?? null

  const starCounts = [5, 4, 3, 2, 1].map((n) => ({
    stars: n,
    count: Math.round((resenas.total || 0) * (n === Math.round(resenas.promedio) ? 0.5 : 0.1)),
  }))

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <div className="max-w-6xl mx-auto px-4 py-6">

        {/* Volver */}
        <motion.button
          onClick={() => navigate(-1)}
          className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full font-sans text-sm text-[var(--color-text-secondary)] border border-[var(--color-border)] hover:border-[#29B6F6]/50 hover:text-[#0277BD] transition-all duration-150 mb-7"
          initial={{ opacity: 0, x: -12 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4, ease }}
        >
          <ArrowLeft size={14} /> Volver al catálogo
        </motion.button>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-10 lg:gap-14">

          {/* ── Columna imagen ── */}
          <motion.div
            className="space-y-3"
            initial={{ opacity: 0, x: -24 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.65, ease }}
          >
            <div className="rounded-2xl overflow-hidden border border-[var(--color-border)] bg-[var(--color-surface)] shadow-[0_4px_24px_rgba(0,0,0,0.06)]">
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
                  <motion.button
                    key={idx}
                    onClick={() => setSelectedImg(idx)}
                    className={`rounded-xl overflow-hidden border-2 transition-all duration-150 aspect-square ${
                      selectedImg === idx
                        ? 'shadow-[0_0_0_2px_#29B6F6]'
                        : 'border-[var(--color-border)] hover:border-[#29B6F6]/50'
                    }`}
                    style={selectedImg === idx ? { borderColor: '#29B6F6' } : undefined}
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.35, ease, delay: idx * 0.06 }}
                    whileHover={{ scale: 1.04 }}
                    whileTap={{ scale: 0.96 }}
                  >
                    <ProductImage
                      src={typeof img === 'string' ? img : img?.url}
                      alt={`${product.nombre} - imagen ${idx + 1}`}
                      categoria={product.categoria}
                      nombre={product.nombre}
                      aspectRatio="aspect-square"
                      size="sm"
                    />
                  </motion.button>
                ))}
              </div>
            )}
          </motion.div>

          {/* ── Columna info ── */}
          <motion.div
            className="space-y-5"
            initial={{ opacity: 0, x: 24 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.65, ease, delay: 0.1 }}
          >
            {/* Badges */}
            <div className="flex items-center gap-2 flex-wrap">
              {(product.categorias || (product.categoria ? [product.categoria] : [])).map(cat => (
                <span
                  key={cat.slug}
                  className="inline-flex items-center px-2.5 py-0.5 rounded-full font-sans text-xs font-semibold text-white"
                  style={{ background: 'linear-gradient(135deg, #29B6F6, #0288D1)' }}
                >
                  {cat.nombre}
                </span>
              ))}
              {displayAvailable ? (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-sans text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  {displayStock > 0 ? `${displayStock} en stock` : 'En stock'}
                </span>
              ) : (
                <Badge variant="error">Sin stock</Badge>
              )}
              {displayAvailable && displayStock > 0 && displayStock <= 5 && (
                <span className="font-sans text-xs font-semibold text-[var(--color-error)]">¡Últimas unidades!</span>
              )}
            </div>

            {/* Nombre */}
            <h1 className="font-display font-bold text-2xl lg:text-[1.85rem] text-[var(--color-text-primary)] leading-tight">
              {product.nombre}
            </h1>

            {/* Estrellas */}
            {resenas.total > 0 && (
              <StarRating value={resenas.promedio} size={16} count={resenas.total} />
            )}

            {/* Precio */}
            <div className="flex items-end gap-3 py-1">
              <span className="font-mono font-bold leading-none" style={{ fontSize: 'clamp(2rem, 5vw, 2.8rem)', color: '#0277BD' }}>
                {displayPrice == null ? '—' : formatQ(displayPrice)}
              </span>
              {product.moneda && (
                <span className="font-sans text-sm text-[var(--color-text-muted)] mb-1">{product.moneda}</span>
              )}
            </div>

            {flashSale && (
              <div className="rounded-2xl border border-amber-300 bg-amber-50 px-4 py-4 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 text-amber-700 font-display font-bold">
                    <Zap size={18} fill="currentColor" /> Venta flash de {flashSale.vendedor_nombre}
                  </div>
                  <span className="font-mono text-sm text-amber-800">
                    {(() => {
                      const secs = Math.max(0, Math.ceil((new Date(flashSale.finaliza_en + 'Z').getTime() - clock) / 1000))
                      const h = Math.floor(secs / 3600)
                      const m = Math.floor((secs % 3600) / 60)
                      const s = secs % 60
                      return h > 0
                        ? `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
                        : `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
                    })()}
                  </span>
                </div>
                <p className="text-sm text-amber-900">
                  <span className="line-through opacity-60 mr-2">{formatQ(flashSale.precio_normal)}</span>
                  <strong>{flashSale.unidades_disponibles} unidades promocionales disponibles</strong>
                </p>
                {flashSale.max_por_usuario > 1 && (
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-amber-800 font-medium">Cantidad:</span>
                    <div className="flex items-center border border-amber-300 rounded-lg overflow-hidden bg-white">
                      <button
                        type="button"
                        className="px-3 py-1.5 text-amber-700 hover:bg-amber-100 transition-colors font-bold"
                        onClick={() => setFlashCantidad(c => Math.max(1, c - 1))}
                      >−</button>
                      <span className="px-4 py-1.5 font-mono font-semibold text-amber-900 text-sm min-w-[2.5rem] text-center">{flashCantidad}</span>
                      <button
                        type="button"
                        className="px-3 py-1.5 text-amber-700 hover:bg-amber-100 transition-colors font-bold"
                        onClick={() => setFlashCantidad(c => Math.min(flashSale.max_por_usuario, flashSale.unidades_disponibles, c + 1))}
                      >+</button>
                    </div>
                    <span className="text-xs text-amber-700">Máx. {flashSale.max_por_usuario} por pedido</span>
                  </div>
                )}
                <Button
                  type="button"
                  className="w-full"
                  disabled={cartLoading || flashSale.unidades_disponibles < 1}
                  onClick={handleFlashReserve}
                >
                  <Zap size={15} /> Reservar {flashSale.max_por_usuario > 1 ? `${flashCantidad} unidad${flashCantidad > 1 ? 'es' : ''}` : 'una unidad'} por 5 minutos
                </Button>
              </div>
            )}

            {/* Vendedor */}
            {displayVendor && (
              <Link
                to={displayVendorId ? `/tienda/${displayVendorId}` : '#'}
                className="flex items-center gap-3 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 w-fit hover:border-[#29B6F6]/50 hover:shadow-[0_4px_16px_rgba(41,182,246,0.1)] transition-all duration-200 group"
              >
                <div className="h-9 w-9 rounded-xl flex items-center justify-center shrink-0" style={{ backgroundColor: 'rgba(41,182,246,0.1)' }}>
                  <Store size={16} style={{ color: '#0288D1' }} strokeWidth={1.5} />
                </div>
                <div>
                  <p className="font-sans text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--color-text-muted)] leading-none mb-0.5">Vendedor · Ver tienda</p>
                  <p className="font-display font-semibold text-sm text-[var(--color-text-primary)] group-hover:text-[#0288D1] transition-colors">
                    {displayVendor}
                  </p>
                </div>
              </Link>
            )}

            {/* Selector de variantes */}
            {mostrarSelector && (
              <div className="space-y-2.5">
                <p className="font-sans text-xs font-bold uppercase tracking-[0.12em] text-[var(--color-text-muted)]">
                  {unicaClave ? unicaClave.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) : 'Variante'}
                </p>
                <div className="flex flex-wrap gap-2">
                  {variantesAgrupadas.map((variant, i) => {
                    const isSelected = selectedVariant?.variante_id === variant.variante_id
                    const attrs = Object.entries(variant.atributos)
                    const label = attrs.length === 0 ? 'Estándar'
                      : unicaClave ? String(variant.atributos[unicaClave])
                      : attrs.map(([k, v]) => `${k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}: ${v}`).join(' · ')
                    const hasStock = variant.ofertas.some(o => (o.stock ?? 0) > 0)
                    return (
                      <motion.button
                        key={variant.variante_id}
                        type="button"
                        onClick={() => {
                          setSelectedVariantId(variant.variante_id)
                          setSelectedOfferId(variant.ofertas[0]?.oferta_id ?? null)
                          setCantidad(1)
                        }}
                        disabled={!hasStock}
                        className="relative rounded-xl border px-4 py-2 text-sm font-sans transition-all duration-150"
                        style={isSelected
                          ? { borderColor: '#29B6F6', backgroundColor: 'rgba(41,182,246,0.06)', color: '#0277BD', fontWeight: 600 }
                          : hasStock
                            ? { borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface)' }
                            : { borderColor: 'var(--color-border)', opacity: 0.4, cursor: 'not-allowed' }
                        }
                        initial={{ opacity: 0, scale: 0.94 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ duration: 0.3, ease, delay: i * 0.05 }}
                        whileTap={hasStock ? { scale: 0.96 } : {}}
                      >
                        {label}
                        {!hasStock && <span className="ml-1.5 text-[10px] text-[var(--color-error)]">Sin stock</span>}
                      </motion.button>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Selector de ofertas (múltiples vendedores) */}
            {ofertasVariante.length > 1 && (
              <div className="space-y-1.5">
                <p className="font-sans text-xs font-bold uppercase tracking-[0.12em] text-[var(--color-text-muted)]">Vendedor</p>
                {ofertasVariante.map((offer) => {
                  const isSelected = selectedOffer?.oferta_id === offer.oferta_id
                  return (
                    <div key={offer.oferta_id} className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => { setSelectedOfferId(offer.oferta_id); setCantidad(1) }}
                        className="flex-1 flex items-center justify-between rounded-xl border px-3 py-2.5 text-left transition-all duration-150"
                        style={isSelected
                          ? { borderColor: '#29B6F6', backgroundColor: 'rgba(41,182,246,0.05)' }
                          : { borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface)' }
                        }
                      >
                        <div className="flex items-center gap-2 flex-wrap">
                          <Store size={13} style={{ color: isSelected ? '#0288D1' : 'var(--color-text-muted)' }} strokeWidth={1.5} />
                          <span className="font-sans text-sm font-medium">{offer.vendedor_nombre}</span>
                          {offer.es_tiendaya && (
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-[var(--color-action)]/10 text-[var(--color-action)]">TiendaYa</span>
                          )}
                          {flashByOfferId[offer.oferta_id] && (
                            <span className="flex items-center gap-0.5 text-[10px] font-bold text-amber-600 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded-full">
                              <Zap size={9} fill="currentColor" /> {formatQ(flashByOfferId[offer.oferta_id].precio_promocional)}
                            </span>
                          )}
                          {(() => { const totalStock = (offer.stock ?? 0) + (flashByOfferId[offer.oferta_id]?.unidades_disponibles ?? 0); return totalStock > 0 && totalStock <= 5 && !flashByOfferId[offer.oferta_id] && <span className="text-[10px] text-amber-500 font-medium">¡Últimas {totalStock}!</span> })()}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-sm font-bold" style={{ color: flashByOfferId[offer.oferta_id] ? '#b45309' : '#0277BD' }}>
                            {flashByOfferId[offer.oferta_id] ? formatQ(flashByOfferId[offer.oferta_id].precio_promocional) : formatQ(offer.precio)}
                          </span>
                          <span className="font-sans text-xs text-[var(--color-text-muted)]">{(offer.stock ?? 0) + (flashByOfferId[offer.oferta_id]?.unidades_disponibles ?? 0)} disp.</span>
                        </div>
                      </button>
                      <Link
                        to={`/tienda/${offer.vendedor_id}`}
                        title={`Ver tienda de ${offer.vendedor_nombre}`}
                        className="h-10 w-10 flex-shrink-0 flex items-center justify-center rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-muted)] transition-all duration-150"
                        style={{ ':hover': { borderColor: '#29B6F6', color: '#0288D1' } }}
                        onMouseEnter={e => { e.currentTarget.style.borderColor = '#29B6F6'; e.currentTarget.style.color = '#0288D1' }}
                        onMouseLeave={e => { e.currentTarget.style.borderColor = ''; e.currentTarget.style.color = '' }}
                      >
                        <Store size={14} strokeWidth={1.5} />
                      </Link>
                    </div>
                  )
                })}
              </div>
            )}

            <CategoryAttrPanel categoria={product.categoria} atributos={atributos} />

            {/* Cantidad + Agregar */}
            <div className="space-y-3 pt-1">
              <div className="flex items-center gap-3">
                {/* Selector cantidad */}
                <div className="flex items-center gap-0 border border-[var(--color-border)] rounded-full h-11 overflow-hidden">
                  <button
                    onClick={() => setCantidad((c) => Math.max(1, c - 1))}
                    className="h-full px-4 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-border)] transition-colors active:scale-[.92]"
                  >
                    <Minus size={14} />
                  </button>
                  <span className="font-mono font-bold text-base w-10 text-center text-[var(--color-text-primary)] select-none">
                    {cantidad}
                  </span>
                  <button
                    onClick={() => setCantidad((c) => Math.min(displayStock || 1, c + 1))}
                    className="h-full px-4 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-border)] transition-colors active:scale-[.92]"
                  >
                    <Plus size={14} />
                  </button>
                </div>

                {/* Botón agregar */}
                <button
                  onClick={handleAdd}
                  disabled={!displayAvailable || cartLoading || Boolean(flashSale)}
                  className="flex-1 h-11 flex items-center justify-center gap-2 rounded-full font-sans font-bold text-sm text-white shadow-[0_4px_20px_rgba(41,182,246,0.35)] transition-all duration-200 hover:shadow-[0_6px_28px_rgba(41,182,246,0.45)] hover:-translate-y-0.5 active:scale-[.97] disabled:opacity-50 disabled:pointer-events-none"
                  style={{ background: 'linear-gradient(135deg, #29B6F6, #0288D1)' }}
                >
                  <ShoppingCart size={17} />
                  {flashSale ? 'Usa la reserva flash' : displayAvailable ? 'Agregar al carrito' : 'Sin stock'}
                </button>
              </div>

              {/* Envío */}
              <div className="flex items-center gap-3 rounded-2xl border px-4 py-3" style={{ borderColor: 'rgba(41,182,246,0.25)', backgroundColor: 'rgba(41,182,246,0.04)' }}>
                <Truck size={16} style={{ color: '#0288D1' }} className="shrink-0" />
                <p className="font-sans text-sm text-[var(--color-text-secondary)]">
                  Envío: <span className="font-semibold text-[var(--color-text-primary)]">Q35–Q75</span> según municipio
                </p>
              </div>

              {/* Garantía */}
              <div className="flex items-center gap-3 rounded-2xl border border-[var(--color-border)] px-4 py-3 bg-[var(--color-surface)]">
                <ShieldCheck size={16} className="text-emerald-500 shrink-0" />
                <p className="font-sans text-sm text-[var(--color-text-secondary)]">
                  Compra protegida — <span className="font-semibold text-[var(--color-text-primary)]">TiendaYa</span> respalda tu pedido
                </p>
              </div>
            </div>
          </motion.div>
        </div>

        {/* ── Secciones inferiores ── */}
        <div className="mt-14 space-y-10">
          <Separator />

          {/* Descripción */}
          <Reveal>
            <section>
              <h2 className="font-display font-bold text-xl text-[var(--color-text-primary)] mb-4">Descripción</h2>
              <p className="font-sans text-base text-[var(--color-text-secondary)] leading-relaxed max-w-3xl">
                {product.descripcion || 'Sin descripción disponible.'}
              </p>
            </section>
          </Reveal>

          <Separator />

          {/* Especificaciones */}
          {Object.keys(atributos).length > 0 && (
            <>
              <Reveal>
                <section>
                  <h2 className="font-display font-bold text-xl text-[var(--color-text-primary)] mb-4">Especificaciones técnicas</h2>
                  <div className="overflow-hidden rounded-2xl border border-[var(--color-border)]">
                    <table className="w-full text-sm">
                      <tbody>
                        {Object.entries(atributos).map(([key, value], idx) => (
                          <tr key={key} className={idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]'}>
                            <td className="px-5 py-3 font-sans font-semibold w-2/5 capitalize border-b border-[var(--color-border)]"
                              style={{ color: '#0277BD' }}>
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
              </Reveal>
              <Separator />
            </>
          )}

          {/* Reseñas Neo4j */}
          <Reveal className="mt-10">
            <div className="border-t border-[var(--color-border)] pt-8">
              <h2 className="font-display font-bold text-xl mb-6">Reseñas del producto</h2>
              <ReviewSection
                productoRef={product?._id}
                vendedorId={selectedOffer?.vendedor_id}
              />
            </div>
          </Reveal>
        </div>
      </div>

      {/* ── Barra sticky móvil ── */}
      {displayAvailable && !flashSale && (
        <motion.div
          className="fixed bottom-0 left-0 right-0 z-40 lg:hidden bg-[var(--color-surface)]/95 backdrop-blur-md border-t border-[var(--color-border)] shadow-[0_-4px_24px_rgba(0,0,0,0.08)] px-4 py-3 flex items-center gap-3"
          initial={{ y: 80, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.5, ease, delay: 0.4 }}
        >
          <div className="flex-1 min-w-0">
            <p className="font-mono font-bold text-xl leading-none" style={{ color: '#0277BD' }}>
              {formatQ(displayPrice)}
            </p>
            <p className="font-sans text-xs text-[var(--color-text-muted)] truncate mt-0.5">
              {product.nombre}
            </p>
          </div>
          <button
            onClick={handleAdd}
            disabled={cartLoading}
            className="flex items-center gap-2 px-5 h-11 rounded-full font-sans font-bold text-sm text-white shadow-[0_4px_16px_rgba(41,182,246,0.4)] active:scale-95 transition-all disabled:opacity-50"
            style={{ background: 'linear-gradient(135deg, #29B6F6, #0288D1)' }}
          >
            <ShoppingCart size={16} /> Agregar
          </button>
        </motion.div>
      )}
    </div>
  )
}
