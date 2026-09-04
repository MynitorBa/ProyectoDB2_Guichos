import { useState, useRef, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Store, Star, Package, ChevronLeft, ChevronRight, Search, X,
  Monitor, Smartphone, Headphones, Shirt, Layers,
  ShoppingBag, BookOpen, Apple, Home, Dumbbell, Wrench, Gamepad2,
} from 'lucide-react'
import api from '../api/client'
import { getProducts, getCategories } from '../api/products'
import { ProductCard } from '../components/product/ProductCard'
import { ProductCardSkeleton } from '../components/ui/skeleton'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { formatDate } from '../lib/utils'

const CATEGORY_ICONS = {
  computadoras: Monitor,
  celulares:    Smartphone,
  audio:        Headphones,
  camisas:      Shirt,
  pantalones:   Layers,
  calzado:      ShoppingBag,
  libros:       BookOpen,
  alimentos:    Apple,
  hogar:        Home,
  deportes:     Dumbbell,
  herramientas: Wrench,
  juguetes:     Gamepad2,
}

export default function VendorStorePage() {
  const { vendedorId } = useParams()
  const [page, setPage] = useState(1)
  const [categoria, setCategoria] = useState(null)
  const [searchInput, setSearchInput] = useState('')
  const [q, setQ] = useState('')
  const carouselRef = useRef(null)

  // Debounce del buscador: espera 350ms tras el último keystroke antes de lanzar la query
  useEffect(() => {
    const timer = setTimeout(() => {
      setQ(searchInput.trim())
      setPage(1)
    }, 350)
    return () => clearTimeout(timer)
  }, [searchInput])

  const { data: vendor, isLoading: loadingVendor, isError: vendorError } = useQuery({
    queryKey: ['store-profile', vendedorId],
    queryFn: () => api.get(`/stores/${vendedorId}`).then(r => r.data),
  })

  const { data: productsData, isLoading: loadingProducts } = useQuery({
    queryKey: ['store-products', vendedorId, page, categoria, q],
    queryFn: () => getProducts({
      vendedor_id: vendedorId,
      page,
      page_size: 12,
      disponible: true,
      ...(categoria && { categoria }),
      ...(q && { q }),
    }).then(r => r.data),
    enabled: !!vendor,
  })

  const { data: categories = [] } = useQuery({
    queryKey: ['categories'],
    queryFn: () => getCategories().then(r => r.data),
  })

  const products = productsData?.items || []
  const totalPages = productsData?.total_pages || 1
  const total = productsData?.total || 0

  function scrollCarousel(dir) {
    if (!carouselRef.current) return
    carouselRef.current.scrollBy({ left: dir * 220, behavior: 'smooth' })
  }

  function handleCategoria(slug) {
    setCategoria(prev => prev === slug ? null : slug)
    setPage(1)
  }

  if (loadingVendor) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-12 space-y-6">
        <div className="h-32 w-full rounded-[var(--radius-xl)] bg-[var(--color-border)] animate-pulse" />
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => <ProductCardSkeleton key={i} />)}
        </div>
      </div>
    )
  }

  if (vendorError || !vendor) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-20 text-center">
        <Store size={56} className="mx-auto mb-4 text-[var(--color-border-strong)]" strokeWidth={1.5} />
        <h2 className="font-display font-bold text-2xl text-[var(--color-text-primary)] mb-2">
          Tienda no encontrada
        </h2>
        <p className="font-sans text-sm text-[var(--color-text-secondary)] mb-6">
          Esta tienda no existe o ya no está disponible.
        </p>
        <Button variant="secondary" asChild>
          <Link to="/catalog">Ver catálogo</Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      {/* ── Encabezado de tienda ── */}
      <section
        className="border-b border-[var(--color-border)]"
        style={{ background: 'linear-gradient(135deg, var(--color-action) 0%, var(--color-jade) 100%)' }}
      >
        <div className="max-w-6xl mx-auto px-4 py-10">
          <div className="flex items-start gap-5 flex-wrap">
            <div className="h-16 w-16 rounded-[var(--radius-xl)] bg-white/20 backdrop-blur-sm flex items-center justify-center flex-shrink-0 shadow-[var(--shadow-md)]">
              <Store size={30} className="text-white" strokeWidth={1.5} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap mb-1">
                <h1 className="font-display font-bold text-2xl lg:text-3xl text-white leading-tight">
                  {vendor.nombre_comercial}
                </h1>
                {vendor.es_tiendaya && (
                  <span className="inline-flex items-center gap-1 text-xs font-semibold bg-amber-400/20 text-amber-200 border border-amber-300/30 px-2.5 py-1 rounded-full">
                    <Star size={11} className="fill-amber-200" /> TiendaYa
                  </span>
                )}
              </div>
              {vendor.descripcion && (
                <p className="font-sans text-sm text-white/80 max-w-xl leading-relaxed mb-2">
                  {vendor.descripcion}
                </p>
              )}
              <div className="flex items-center gap-4 flex-wrap">
                {total > 0 && (
                  <span className="font-sans text-xs text-white/70">
                    <strong className="text-white">{total}</strong> producto{total !== 1 ? 's' : ''} disponibles
                  </span>
                )}
                {vendor.fecha_registro && (
                  <span className="font-sans text-xs text-white/70">
                    En TiendaYa desde <strong className="text-white">{formatDate(vendor.fecha_registro)}</strong>
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="max-w-6xl mx-auto px-4 py-8 space-y-8">
        {/* ── Buscador ── */}
        <div className="relative max-w-md">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] pointer-events-none" />
          <input
            type="search"
            aria-label="Buscar en esta tienda"
            placeholder={`Buscar en ${vendor.nombre_comercial}…`}
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            className="w-full pl-9 pr-9 py-2.5 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] font-sans text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-action)]/30 focus:border-[var(--color-action)] transition-colors"
          />
          {searchInput && (
            <button
              onClick={() => setSearchInput('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
              aria-label="Limpiar búsqueda"
            >
              <X size={14} />
            </button>
          )}
        </div>

        {/* ── Filtro de categorías ── */}
        {categories.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                Filtrar por categoría
              </p>
              <div className="flex gap-1.5">
                <button
                  onClick={() => scrollCarousel(-1)}
                  className="h-7 w-7 flex items-center justify-center rounded-full border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] transition-colors"
                >
                  <ChevronLeft size={14} />
                </button>
                <button
                  onClick={() => scrollCarousel(1)}
                  className="h-7 w-7 flex items-center justify-center rounded-full border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] transition-colors"
                >
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>
            <div
              ref={carouselRef}
              className="flex gap-2 overflow-x-auto pb-1"
              style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
            >
              <button
                onClick={() => handleCategoria(null)}
                className={`flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-sm font-sans font-medium transition-all ${
                  categoria === null
                    ? 'bg-[var(--color-action)] border-[var(--color-action)] text-white'
                    : 'border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)] hover:border-[var(--color-action)] hover:text-[var(--color-action)]'
                }`}
              >
                Todos
              </button>
              {categories.map(cat => {
                const Icon = CATEGORY_ICONS[cat.slug] || Package
                const isActive = categoria === cat.slug
                return (
                  <button
                    key={cat.slug}
                    onClick={() => handleCategoria(cat.slug)}
                    className={`flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-sm font-sans font-medium transition-all ${
                      isActive
                        ? 'bg-[var(--color-action)] border-[var(--color-action)] text-white'
                        : 'border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)] hover:border-[var(--color-action)] hover:text-[var(--color-action)]'
                    }`}
                  >
                    <Icon size={13} />
                    {cat.nombre}
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {/* ── Grid de productos ── */}
        {loadingProducts ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {Array.from({ length: 12 }).map((_, i) => <ProductCardSkeleton key={i} />)}
          </div>
        ) : products.length > 0 ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
              {products.map(product => (
                <ProductCard key={product._id} product={product} vendedorId={vendedorId} />
              ))}
            </div>

            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-3 pt-2">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page === 1}
                  onClick={() => setPage(p => p - 1)}
                >
                  <ChevronLeft size={14} /> Anterior
                </Button>
                <span className="font-sans text-sm text-[var(--color-text-secondary)]">
                  {page} / {totalPages}
                </span>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage(p => p + 1)}
                >
                  Siguiente <ChevronRight size={14} />
                </Button>
              </div>
            )}
          </>
        ) : (
          <div className="text-center py-20">
            <Package size={56} className="mx-auto mb-4 text-[var(--color-border-strong)]" strokeWidth={1.5} />
            <h3 className="font-display font-semibold text-lg text-[var(--color-text-primary)] mb-2">
              {q ? `Sin resultados para "${q}"` : categoria ? 'Sin productos en esta categoría' : 'Sin productos disponibles'}
            </h3>
            <p className="font-sans text-sm text-[var(--color-text-secondary)] mb-4">
              {q
                ? 'Intenta con otras palabras o limpia el buscador.'
                : categoria
                ? 'Esta tienda no tiene productos disponibles en la categoría seleccionada.'
                : 'Esta tienda no tiene productos disponibles en este momento.'}
            </p>
            {(q || categoria) && (
              <div className="flex justify-center gap-2 flex-wrap">
                {q && (
                  <Button variant="secondary" size="sm" onClick={() => setSearchInput('')}>
                    Limpiar búsqueda
                  </Button>
                )}
                {categoria && (
                  <Button variant="secondary" size="sm" onClick={() => setCategoria(null)}>
                    Ver todas las categorías
                  </Button>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
