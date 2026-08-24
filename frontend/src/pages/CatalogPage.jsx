import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { SlidersHorizontal, X, ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { getProducts, getCategories } from '../api/products'
import { ProductCard } from '../components/product/ProductCard'
import { ProductCardSkeleton } from '../components/ui/skeleton'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Sheet, SheetTrigger, SheetContent } from '../components/ui/sheet'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../components/ui/select'
import { Separator } from '../components/ui/separator'

const SORT_OPTIONS = [
  { value: 'reciente', label: 'Más recientes' },
  { value: 'precio_asc', label: 'Precio: menor a mayor' },
  { value: 'precio_desc', label: 'Precio: mayor a menor' },
]

function FiltersPanel({ categories, filters, onFilterChange, onClear }) {
  return (
    <div className="space-y-6">
      <div>
        <Label className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
          Categoría
        </Label>
        <div className="mt-2 flex flex-col gap-1">
          <button
            onClick={() => onFilterChange('categoria', '')}
            className={`text-left px-3 py-1.5 rounded-[var(--radius-md)] text-sm font-sans transition-colors ${
              !filters.categoria
                ? 'bg-[var(--color-action)] text-white font-semibold'
                : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-border)]'
            }`}
          >
            Todas las categorías
          </button>
          {categories.map((cat) => (
            <button
              key={cat.slug}
              onClick={() => onFilterChange('categoria', cat.slug)}
              className={`text-left px-3 py-1.5 rounded-[var(--radius-md)] text-sm font-sans transition-colors ${
                filters.categoria === cat.slug
                  ? 'bg-[var(--color-action)] text-white font-semibold'
                  : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-border)]'
              }`}
            >
              {cat.nombre}
            </button>
          ))}
        </div>
      </div>

      <Separator />

      <div>
        <Label className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
          Precio (GTQ)
        </Label>
        <div className="mt-2 flex gap-2 items-center">
          <Input
            type="number"
            placeholder="Mín"
            value={filters.precio_min}
            onChange={(e) => onFilterChange('precio_min', e.target.value)}
          />
          <span className="text-[var(--color-text-muted)] text-sm">–</span>
          <Input
            type="number"
            placeholder="Máx"
            value={filters.precio_max}
            onChange={(e) => onFilterChange('precio_max', e.target.value)}
          />
        </div>
      </div>

      <Separator />

      <div>
        <Label className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
          Ordenar por
        </Label>
        <div className="mt-2">
          <Select value={filters.sort} onValueChange={(v) => onFilterChange('sort', v)}>
            <SelectTrigger>
              <SelectValue placeholder="Seleccionar orden" />
            </SelectTrigger>
            <SelectContent>
              {SORT_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <Button variant="ghost" size="sm" className="w-full" onClick={onClear}>
        <X size={14} /> Limpiar filtros
      </Button>
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

  // Sync filters when URL params change (e.g. user clicks a category in the header)
  useEffect(() => {
    setFilters((prev) => ({ ...prev, categoria }))
    setPage(1)
  }, [categoria])

  useEffect(() => {
    setLocalSearch(q)
  }, [q])

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

  const hasActiveFilters =
    filters.categoria || filters.precio_min || filters.precio_max || q

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-6 flex-wrap gap-4">
          <div>
            <h1 className="font-display font-bold text-2xl text-[var(--color-text-primary)]">
              {filters.categoria
                ? categories.find((c) => c.slug === filters.categoria)?.nombre || 'Catálogo'
                : 'Catálogo'}
            </h1>
            {data?.total !== undefined && (
              <p className="font-sans text-sm text-[var(--color-text-secondary)] mt-0.5">
                {data.total} producto{data.total !== 1 ? 's' : ''} encontrado{data.total !== 1 ? 's' : ''}
              </p>
            )}
          </div>

          <form onSubmit={handleSearch} className="flex gap-2 w-full sm:w-auto">
            <Input
              placeholder="Buscar productos..."
              value={localSearch}
              onChange={(e) => setLocalSearch(e.target.value)}
              className="w-full sm:w-64"
            />
            <Button type="submit" size="icon" variant="secondary">
              <Search size={16} />
            </Button>
          </form>
        </div>

        <div className="flex gap-6">
          <aside className="hidden lg:block w-56 shrink-0">
            <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5 sticky top-20">
              <h2 className="font-display font-semibold text-base text-[var(--color-text-primary)] mb-4">
                Filtros
              </h2>
              <FiltersPanel
                categories={categories}
                filters={filters}
                onFilterChange={updateFilter}
                onClear={clearFilters}
              />
            </div>
          </aside>

          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between mb-4 lg:hidden">
              <Sheet>
                <SheetTrigger asChild>
                  <Button variant="secondary" size="sm">
                    <SlidersHorizontal size={14} /> Filtros
                    {hasActiveFilters && (
                      <span className="ml-1 h-4 w-4 rounded-full bg-[var(--color-action)] text-white text-[10px] flex items-center justify-center">
                        !
                      </span>
                    )}
                  </Button>
                </SheetTrigger>
                <SheetContent side="left" title="Filtros">
                  <div className="p-5">
                    <FiltersPanel
                      categories={categories}
                      filters={filters}
                      onFilterChange={updateFilter}
                      onClear={clearFilters}
                    />
                  </div>
                </SheetContent>
              </Sheet>
            </div>

            {isError && (
              <div className="rounded-[var(--radius-md)] bg-[var(--color-error)]/10 border border-[var(--color-error)]/30 px-4 py-3 mb-4">
                <p className="text-sm font-sans text-[var(--color-error)]">
                  Error al cargar los productos. Intenta de nuevo.
                </p>
              </div>
            )}

            {isLoading ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-4">
                {Array.from({ length: 12 }).map((_, i) => (
                  <ProductCardSkeleton key={i} />
                ))}
              </div>
            ) : products.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-24 text-center">
                <Search size={48} className="text-[var(--color-border-strong)] mb-4" strokeWidth={1.5} />
                <h3 className="font-display font-semibold text-lg text-[var(--color-text-primary)] mb-2">
                  Sin resultados
                </h3>
                <p className="font-sans text-sm text-[var(--color-text-secondary)] mb-6 max-w-xs">
                  No encontramos productos con esos criterios. Intenta con otros filtros.
                </p>
                <Button variant="secondary" onClick={clearFilters}>
                  <X size={14} /> Limpiar filtros
                </Button>
              </div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-4">
                {products.map((product) => (
                  <ProductCard key={product._id} product={product} />
                ))}
              </div>
            )}

            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-3 mt-8">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  <ChevronLeft size={14} /> Anterior
                </Button>
                <span className="font-sans text-sm text-[var(--color-text-secondary)]">
                  Página {page} de {totalPages}
                </span>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Siguiente <ChevronRight size={14} />
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
