import { Link } from 'react-router-dom'
import { ShoppingCart, Check, Zap, Clock3 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button } from '../ui/button'
import { StarRating } from '../ui/star-rating'
import { ProductImage } from './ProductImage'
import { formatQ } from '../../lib/utils'
import { useCart } from '../../context/CartContext'
import { useAuth } from '../../context/AuthContext'
import { toast } from 'sonner'
import { reserveFlashSale } from '../../api/products'

export function ProductCard({ product, vendedorId }) {
  const { add, fetchCart } = useCart()
  const { user } = useAuth()
  const [added, setAdded] = useState(false)
  const [adding, setAdding] = useState(false)

  const firstImage = product.imagenes?.[0]
  const imgSrc = typeof firstImage === 'string' ? firstImage : firstImage?.url || null
  const resenas = product.resumen_resenas || {}
  const categoria = product.categoria
  const flash = product.flash
  const [flashSeconds, setFlashSeconds] = useState(() => flash
    ? Math.max(0, Math.floor((new Date(`${flash.finaliza_en}Z`).getTime() - Date.now()) / 1000))
    : 0)

  useEffect(() => {
    if (!flash) return undefined
    const tick = () => setFlashSeconds(Math.max(0, Math.floor((new Date(`${flash.finaliza_en}Z`).getTime() - Date.now()) / 1000)))
    tick()
    const timer = window.setInterval(tick, 1000)
    return () => window.clearInterval(timer)
  }, [flash])

  const countdown = `${String(Math.floor(flashSeconds / 3600)).padStart(2, '0')}:${String(Math.floor((flashSeconds % 3600) / 60)).padStart(2, '0')}:${String(flashSeconds % 60).padStart(2, '0')}`

  async function handleAdd(e) {
    e.preventDefault()
    if (!user) { toast.error('Inicia sesión para agregar al carrito'); return }
    if (!product.oferta_id) { toast.error('Producto no disponible para compra'); return }
    setAdding(true)
    try {
      if (flash) {
        await reserveFlashSale(flash.id)
        await fetchCart()
      } else {
        await add(product.oferta_id, 1)
      }
      setAdded(true)
      toast.success(flash ? 'Oferta flash reservada durante cinco minutos.' : `${product.nombre} agregado al carrito`)
      setTimeout(() => setAdded(false), 2200)
    } catch (error) {
      toast.error(error.response?.data?.detail || (flash ? 'No se pudo reservar la oferta flash.' : 'No se pudo agregar al carrito'))
    } finally {
      setAdding(false)
    }
  }

  return (
    <Link
      to={`/products/${product._id}${vendedorId ? `?desde_tienda=${vendedorId}` : ''}`}
      className="group flex flex-col bg-[var(--color-surface)] rounded-2xl overflow-hidden border border-[var(--color-border)] hover:border-[#29B6F6]/35 hover:shadow-[0_20px_48px_rgba(41,182,246,0.10),0_4px_16px_rgba(0,0,0,0.08)] hover:-translate-y-1 transition-all duration-300 focus-visible:outline-2 focus-visible:outline-[#29B6F6]"
      style={{ transitionTimingFunction: 'cubic-bezier(0.23,1,0.32,1)' }}
    >
      {/* Imagen */}
      <div className="relative overflow-hidden bg-[var(--color-background)]">
        <div
          className="group-hover:scale-[1.05] transition-transform duration-500"
          style={{ transitionTimingFunction: 'cubic-bezier(0.23,1,0.32,1)' }}
        >
          <ProductImage
            src={imgSrc}
            alt={product.nombre}
            categoria={categoria}
            nombre={product.nombre}
            aspectRatio="aspect-square"
          />
        </div>

        {/* Categoría — pill sobre la imagen */}
        {(categoria?.nombre || product.vendedor_nombre) && (
          <span className="absolute top-2.5 left-2.5 font-sans text-[10px] font-semibold text-white bg-black/45 backdrop-blur-sm px-2 py-0.5 rounded-full pointer-events-none">
            {categoria?.nombre || product.vendedor_nombre}
          </span>
        )}

        {flash && flashSeconds > 0 && (
          <span className="absolute top-2.5 right-2.5 flex items-center gap-1 font-sans text-[10px] font-bold text-amber-950 bg-amber-300 px-2 py-1 rounded-full shadow-sm">
            <Zap size={10} fill="currentColor" /> -{flash.descuento_porcentaje}%
          </span>
        )}

        {/* Sin stock overlay */}
        {!product.disponible && (
          <div className="absolute inset-0 bg-[var(--color-surface)]/80 backdrop-blur-[2px] flex items-center justify-center">
            <span className="font-sans font-semibold text-xs text-[var(--color-text-secondary)] px-3 py-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)]">
              Sin stock
            </span>
          </div>
        )}

        {/* Badge "¡Solo X!" */}
        {!flash && product.stock !== undefined && product.stock !== null && product.disponible && product.stock > 0 && product.stock <= 5 && (
          <span className="absolute top-2.5 right-2.5 font-sans text-[10px] font-bold text-white bg-[var(--color-error)] px-2 py-0.5 rounded-full shadow-sm">
            ¡Solo {product.stock}!
          </span>
        )}

        {/* Botón rápido add — aparece en hover */}
        <div className="absolute bottom-0 inset-x-0 translate-y-full group-hover:translate-y-0 transition-transform duration-300 p-2" style={{ transitionTimingFunction: 'cubic-bezier(0.23,1,0.32,1)' }}>
          <button
            onClick={handleAdd}
            disabled={!product.disponible || adding || (flash && flashSeconds < 1)}
            className="w-full flex items-center justify-center gap-1.5 h-9 rounded-xl font-sans font-semibold text-[13px] text-white shadow-lg transition-opacity duration-150 disabled:opacity-50"
            style={{ background: added ? '#16a34a' : 'linear-gradient(135deg, #29B6F6, #0288D1)' }}
          >
            {added
              ? <><Check size={13} strokeWidth={2.5} /> Agregado</>
              : flash
                ? <><Zap size={13} fill="currentColor" /> Reservar oferta</>
                : <><ShoppingCart size={13} /> Agregar al carrito</>
            }
          </button>
        </div>
      </div>

      {/* Info */}
      <div className="flex flex-col flex-1 px-3.5 pt-3 pb-4 gap-1">
        <h3 className="font-display font-semibold text-[13px] text-[var(--color-text-primary)] line-clamp-2 leading-snug min-h-[2.5rem]">
          {product.nombre}
        </h3>

        {resenas.total > 0 && (
          <StarRating value={resenas.promedio} size={11} count={resenas.total} />
        )}

        {flash && (
          <div className="flex items-center justify-between gap-2 text-[10px] font-sans text-amber-700 bg-amber-50 rounded-lg px-2 py-1.5">
            <span className="flex items-center gap-1"><Clock3 size={10} /> {flashSeconds > 0 ? countdown : 'Finalizada'}</span>
            <span>{flash.unidades_disponibles} disponible{flash.unidades_disponibles !== 1 ? 's' : ''}</span>
          </div>
        )}

        <div className="mt-auto pt-2 flex items-center justify-between gap-2">
          <div>
            {flash && <span className="block font-mono text-[11px] text-[var(--color-text-muted)] line-through">{formatQ(product.precio_normal)}</span>}
            <span className="font-mono font-bold text-[16px] tabular-nums" style={{ color: flash ? '#b45309' : '#0277BD' }}>
              {formatQ(product.precio)}
            </span>
          </div>
          {!product.disponible && (
            <span className="font-sans text-[11px] text-[var(--color-text-muted)]">No disponible</span>
          )}
        </div>
      </div>
    </Link>
  )
}
