import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import {
  SlidersHorizontal, X, ChevronLeft, ChevronRight, Search,
  Monitor, Smartphone, Headphones, Shirt, Layers, ShoppingBag,
  BookOpen, Apple, Home, Dumbbell, Wrench, Gamepad2,
} from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'
import { getProducts, getCategories } from '../api/products'
import { ProductCard } from '../components/product/ProductCard'
import { ProductCardSkeleton } from '../components/ui/skeleton'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Sheet, SheetTrigger, SheetContent } from '../components/ui/sheet'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../components/ui/select'
import { Separator } from '../components/ui/separator'

const ease = [0.23, 1, 0.32, 1]

const ICON_BY_SLUG = {
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
const DEFAULT_ICON = Layers

const SORT_OPTIONS = [
  { value: 'reciente',    label: 'Más recientes' },
  { value: 'precio_asc',  label: 'Precio: menor a mayor' },
  { value: 'precio_desc', label: 'Precio: mayor a menor' },
]

function FiltersPanel({ categories, filters, onFilterChange, onClear }) {
  return (
    <div className="space-y-5">

      {/* Categorías */}
      <div>
        <p className="font-sans text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--color-text-muted)] mb-2.5">
          Categoría
        </p>
        <div className="flex flex-col gap-0.5">
          <button
            onClick={() => onFilterChange('categoria', '')}
            className={`flex items-center gap-2.5 text-left px-3 py-2 rounded-xl text-sm font-sans transition-all duration-150 ${
              !filters.categoria
                ? 'text-white font-semibold shadow-sm'
                : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] hover:text-[var(--color-text-primary)]'
            }`}
            style={!filters.categoria ? { background: 'linear-gradient(135deg, #29B6F6, #0288D1)' } : undefined}
          >
            <Layers size={14} className="shrink-0" />
            Todas las categorías
          </button>
          {categories.map((cat) => {
            const Icon = ICON_BY_SLUG[cat.slug] || DEFAULT_ICON
            const active = filters.categoria === cat.slug
            return (
              <button
                key={cat.slug}
                onClick={() => onFilterChange('categoria', cat.slug)}
                className={`flex items-center gap-2.5 text-left px-3 py-2 rounded-xl text-sm font-sans transition-all duration-150 ${
                  active
                    ? 'text-white font-semibold shadow-sm'
                    : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] hover:text-[var(--color-text-primary)]'
                }`}
                style={active ? { background: 'linear-gradient(135deg, #29B6F6, #0288D1)' } : undefined}
              >
                <Icon size={14} className="shrink-0" strokeWidth={1.5} />
                {cat.nombre}
              </button>
            )
          })}
        </div>
      </div>

      <Separator />

      {/* Precio */}
      <div>
        <p className="font-sans text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--color-text-muted)] mb-2.5">
          Precio (GTQ)
        </p>
        <div className="flex gap-2 items-center">
          <Input
            type="number"
            placeholder="Mín"
            value={filters.precio_min}
            onChange={(e) => onFilterChange('precio_min', e.target.value)}
            className="text-center"
          />
          <span className="text-[var(--color-text-muted)] text-sm font-sans shrink-0">–</span>
          <Input
            type="number"
            placeholder="Máx"
            value={filters.precio_max}
            onChange={(e) => onFilterChange('precio_max', e.target.value)}
            className="text-center"
          />
        </div>
      </div>

      <Separator />

      {/* Ordenar */}
      <div>
        <p className="font-sans text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--color-text-muted)] mb-2.5">
          Ordenar por
        </p>
        <Select value={filters.sort} onValueChange={(v) => onFilterChange('sort', v)}>
          <SelectTrigger>
            <SelectValue placeholder="Seleccionar orden" />
          </SelectTrigger>
          <SelectContent>
            {SORT_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <button
        onClick={onClear}
        className="w-full flex items-center justify-center gap-1.5 py-2 rounded-xl font-sans text-sm text-[var(--color-text-muted)] hover:text-[var(--color-error)] hover:bg-[var(--color-error)]/8 border border-[var(--color-border)] transition-all duration-150"
      >
        <X size={13} /> Limpiar filtros
      </button>
    </div>
  )
}

export default function CatalogPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [page, setPage] = useState(1)

  const categoria = searchParams.get('categoria') || ''
  const q = searchParams.get('q') || ''

  const [localSearch, setLocalSearch] = useState(q)
  const [filters, setFilters] = useState({
    categoria,
    precio_min: '',
    precio_max: '',
    sort: 'reciente',
  })

  useEffect(() => {
    setFilters((prev) => ({ ...prev, categoria }))
    setPage(1)
  }, [categoria])

  useEffect(() => { setLocalSearch(q) }, [q])

  function updateFilter(key, value) {
    setFilters((prev) => ({ ...prev, [key]: value }))
    setPage(1)
    if (key === 'categoria') {
      const next = new URLSearchParams(searchParams)
      if (value) next.set('categoria', value)
      else next.delete('categoria')
      setSearchParams(next)
    }
  }

  function clearFilters() {
    setFilters({ categoria: '', precio_min: '', precio_max: '', sort: 'reciente' })
    setLocalSearch('')
    setSearchParams({})
    setPage(1)
  }

  function handleSearch(e) {
    e.preventDefault()
    const next = new URLSearchParams(searchParams)
    if (localSearch) next.set('q', localSearch)
    else next.delete('q')
    setSearchParams(next)
    setPage(1)
  }

  const queryParams = {
    page,
    page_size: 12,
    ...(filters.categoria && { categoria: filters.categoria }),
    ...(q && { q }),
    ...(filters.precio_min && { precio_min: filters.precio_min }),
    ...(filters.precio_max && { precio_max: filters.precio_max }),
    ...(filters.sort && { orden: filters.sort }),
  }

  const { data, isLoading, isError } = useQuery({
    queryKey: ['products', 'catalog', queryParams],
    queryFn: () => getProducts(queryParams).then((r) => r.data),
    placeholderData: keepPreviousData,
  })

  const { data: categoriesData } = useQuery({
    queryKey: ['categories'],
    queryFn: () => getCategories().then((r) => r.data),
  })

  const products = data?.items || []
  const totalPages = data?.total_pages || 1
  const categories = categoriesData || []

  const activeCategory = categories.find((c) => c.slug === filters.categoria)
  const hasActiveFilters = filters.categoria || filters.precio_min || filters.precio_max || q

  const gridKey = `${filters.categoria}-${q}-${filters.sort}-${page}`

  // Páginas a mostrar (máx 5)
  function getPageRange() {
    const range = []
    const delta = 2
    for (let i = Math.max(1, page - delta); i <= Math.min(totalPages, page + delta); i++) {
      range.push(i)
    }
    return range
  }

  return (
    <div className="min-h-screen bg-[var(--color-background)]">

      {/* ── Banner superior ── */}
      <div
        className="relative overflow-hidden py-10 px-6"
        style={{ background: 'linear-gradient(135deg, #29B6F6 0%, #0288D1 60%, #01579B 100%)' }}
      >
        <div className="absolute inset-0 pointer-events-none opacity-[0.08]"
          style={{ backgroundImage: 'radial-gradient(ellipse at 80% 50%, white 0%, transparent 55%)' }} />
        <div className="max-w-7xl mx-auto relative flex items-center justify-between gap-6">
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease }}
          >
            <p className="font-sans text-[11px] font-semibold uppercase tracking-[0.18em] text-white/60 mb-1">
              TiendaYa
            </p>
            <h1 className="font-display font-bold text-white leading-tight" style={{ fontSize: 'clamp(1.6rem, 4vw, 2.4rem)', letterSpacing: '-0.02em' }}>
              {activeCategory ? activeCategory.nombre : q ? `"${q}"` : 'Catálogo de productos'}
            </h1>
            {data?.total !== undefined && (
              <p className="font-sans text-sm text-white/65 mt-1">
                <span className="font-mono tabular-nums font-semibold text-white">{data.total}</span> producto{data.total !== 1 ? 's' : ''} encontrado{data.total !== 1 ? 's' : ''}
              </p>
            )}
          </motion.div>

          {/* Logo derecha */}
          <motion.img
            src="/TiendaYAlogo.png"
            alt="TiendaYa"
            className="hidden sm:block shrink-0 object-contain drop-shadow-2xl"
            style={{ height: 'clamp(80px, 12vw, 140px)', opacity: 0.92 }}
            initial={{ opacity: 0, x: 24 }}
            animate={{ opacity: 0.92, x: 0 }}
            transition={{ duration: 0.6, ease, delay: 0.1 }}
          />
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 py-8">

        {/* ── Toolbar ── */}
        <motion.div
          className="flex items-center justify-between mb-6 gap-4 flex-wrap"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease, delay: 0.1 }}
        >
          {/* Filtros activos como chips */}
          <div className="flex items-center gap-2 flex-wrap">
            {hasActiveFilters && (
              <>
                {filters.categoria && activeCategory && (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full font-sans text-xs font-semibold text-white" style={{ background: 'linear-gradient(135deg, #29B6F6, #0288D1)' }}>
                    {activeCategory.nombre}
                    <button onClick={() => updateFilter('categoria', '')} className="hover:opacity-70"><X size={11} /></button>
                  </span>
                )}
                {q && (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full font-sans text-xs font-semibold bg-[var(--color-border)] text-[var(--color-text-secondary)]">
                    "{q}"
                    <button onClick={() => { const n = new URLSearchParams(searchParams); n.delete('q'); setSearchParams(n); setLocalSearch('') }} className="hover:opacity-70"><X size={11} /></button>
                  </span>
                )}
                {(filters.precio_min || filters.precio_max) && (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full font-sans text-xs font-semibold bg-[var(--color-border)] text-[var(--color-text-secondary)]">
                    Q{filters.precio_min || '0'} – Q{filters.precio_max || '∞'}
                    <button onClick={() => { updateFilter('precio_min', ''); updateFilter('precio_max', '') }} className="hover:opacity-70"><X size={11} /></button>
                  </span>
                )}
              </>
            )}
            {!hasActiveFilters && (
              <p className="font-sans text-sm text-[var(--color-text-muted)]">Todos los productos</p>
            )}
          </div>

          {/* Search + filtros móvil */}
          <div className="flex items-center gap-2">
            <form onSubmit={handleSearch} className="flex gap-2">
              <div className="relative hidden sm:block">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] pointer-events-none" />
                <input
                  placeholder="Buscar..."
                  value={localSearch}
                  onChange={(e) => setLocalSearch(e.target.value)}
                  className="h-9 pl-8 pr-4 w-52 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-full font-sans text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[#29B6F6] focus:ring-2 focus:ring-[#29B6F6]/20 transition-all"
                />
              </div>
              <button type="submit" className="sm:hidden h-9 w-9 flex items-center justify-center rounded-full bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[#29B6F6]">
                <Search size={16} />
              </button>
            </form>

            <Sheet>
              <SheetTrigger asChild>
                <button className="lg:hidden h-9 px-3.5 flex items-center gap-1.5 rounded-full bg-[var(--color-surface)] border border-[var(--color-border)] font-sans text-sm text-[var(--color-text-secondary)] hover:border-[#29B6F6]/40 transition-colors">
                  <SlidersHorizontal size={14} />
                  Filtros
                  {hasActiveFilters && (
                    <span className="h-4 w-4 rounded-full text-white text-[9px] flex items-center justify-center font-bold" style={{ backgroundColor: '#29B6F6' }}>!</span>
                  )}
                </button>
              </SheetTrigger>
              <SheetContent side="left" title="Filtros">
                <div className="p-5">
                  <FiltersPanel categories={categories} filters={filters} onFilterChange={updateFilter} onClear={clearFilters} />
                </div>
              </SheetContent>
            </Sheet>
          </div>
        </motion.div>

        <div className="flex gap-6">

          {/* ── Sidebar desktop ── */}
          <motion.aside
            className="hidden lg:block w-56 shrink-0"
            initial={{ opacity: 0, x: -16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, ease, delay: 0.12 }}
          >
            <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl p-4 sticky top-24">
              <div className="flex items-center justify-between mb-4">
                <span className="font-sans text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--color-text-muted)]">Filtros</span>
                {hasActiveFilters && (
                  <button onClick={clearFilters} className="font-sans text-[11px] text-[#29B6F6] hover:underline">Limpiar</button>
                )}
              </div>
              <FiltersPanel categories={categories} filters={filters} onFilterChange={updateFilter} onClear={clearFilters} />
            </div>
          </motion.aside>

          {/* ── Grid ── */}
          <div className="flex-1 min-w-0">
            {isError && (
              <div className="rounded-2xl bg-[var(--color-error)]/10 border border-[var(--color-error)]/30 px-4 py-3 mb-5">
                <p className="text-sm font-sans text-[var(--color-error)]">Error al cargar los productos. Intenta de nuevo.</p>
              </div>
            )}

            {isLoading ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-4 lg:gap-5">
                {Array.from({ length: 12 }).map((_, i) => <ProductCardSkeleton key={i} />)}
              </div>
            ) : products.length === 0 ? (
              <motion.div
                className="flex flex-col items-center justify-center py-28 text-center"
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.45, ease }}
              >
                <div className="h-20 w-20 rounded-full flex items-center justify-center mb-5" style={{ background: 'linear-gradient(135deg, #29B6F6/10, #0288D1/10)', backgroundColor: 'rgba(41,182,246,0.08)' }}>
                  <Search size={32} className="text-[#29B6F6]" strokeWidth={1.5} />
                </div>
                <h3 className="font-display font-bold text-xl text-[var(--color-text-primary)] mb-2">Sin resultados</h3>
                <p className="font-sans text-sm text-[var(--color-text-secondary)] mb-6 max-w-xs">
                  No encontramos productos con esos criterios. Prueba con otros filtros.
                </p>
                <button
                  onClick={clearFilters}
                  className="flex items-center gap-1.5 px-5 py-2.5 rounded-full font-sans font-semibold text-sm text-white transition-opacity hover:opacity-88"
                  style={{ background: 'linear-gradient(135deg, #29B6F6, #0288D1)' }}
                >
                  <X size={13} /> Limpiar filtros
                </button>
              </motion.div>
            ) : (
              <div key={gridKey} className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-4 lg:gap-5">
                {products.map((product, i) => (
                  <motion.div
                    key={product._id}
                    initial={{ opacity: 0, y: 18 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.45, ease, delay: Math.min(i * 0.05, 0.35) }}
                  >
                    <ProductCard product={product} />
                  </motion.div>
                ))}
              </div>
            )}

            {/* ── Paginación ── */}
            {totalPages > 1 && (
              <motion.div
                className="flex items-center justify-center gap-1.5 mt-12"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.4, ease, delay: 0.3 }}
              >
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
                  className="h-9 w-9 flex items-center justify-center rounded-full border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[#29B6F6]/40 hover:text-[#29B6F6] disabled:opacity-40 disabled:pointer-events-none transition-all"
                >
                  <ChevronLeft size={15} />
                </button>

                {page > 3 && (
                  <>
                    <button onClick={() => setPage(1)} className="h-9 w-9 flex items-center justify-center rounded-full border border-[var(--color-border)] font-mono text-sm text-[var(--color-text-secondary)] hover:border-[#29B6F6]/40 hover:text-[#29B6F6] transition-all">1</button>
                    {page > 4 && <span className="text-[var(--color-text-muted)] text-sm px-1">…</span>}
                  </>
                )}

                {getPageRange().map((p) => (
                  <button
                    key={p}
                    onClick={() => setPage(p)}
                    className="h-9 w-9 flex items-center justify-center rounded-full font-mono text-sm font-semibold transition-all"
                    style={p === page
                      ? { background: 'linear-gradient(135deg, #29B6F6, #0288D1)', color: 'white' }
                      : undefined
                    }
                    {...(p !== page && {
                      className: 'h-9 w-9 flex items-center justify-center rounded-full font-mono text-sm border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[#29B6F6]/40 hover:text-[#29B6F6] transition-all'
                    })}
                  >
                    {p}
                  </button>
                ))}

                {page < totalPages - 2 && (
                  <>
                    {page < totalPages - 3 && <span className="text-[var(--color-text-muted)] text-sm px-1">…</span>}
                    <button onClick={() => setPage(totalPages)} className="h-9 w-9 flex items-center justify-center rounded-full border border-[var(--color-border)] font-mono text-sm text-[var(--color-text-secondary)] hover:border-[#29B6F6]/40 hover:text-[#29B6F6] transition-all">{totalPages}</button>
                  </>
                )}

                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                  className="h-9 w-9 flex items-center justify-center rounded-full border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[#29B6F6]/40 hover:text-[#29B6F6] disabled:opacity-40 disabled:pointer-events-none transition-all"
                >
                  <ChevronRight size={15} />
                </button>
              </motion.div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
