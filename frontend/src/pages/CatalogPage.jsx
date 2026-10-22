import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import {
  SlidersHorizontal, X, ChevronLeft, ChevronRight, Search,
  Monitor, Smartphone, Headphones, Shirt, Layers, ShoppingBag,
  BookOpen, Apple, Home, Dumbbell, Wrench, Gamepad2,
  Zap, PackageCheck, BadgeCheck, Check, AlertTriangle, Sparkles,
} from 'lucide-react'
import { motion } from 'motion/react'
import { searchProducts } from '../api/search'
import { ProductCard } from '../components/product/ProductCard'
import { ProductCardSkeleton } from '../components/ui/skeleton'
import { Input } from '../components/ui/input'
import { Sheet, SheetTrigger, SheetContent } from '../components/ui/sheet'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../components/ui/select'
import { Separator } from '../components/ui/separator'
import { EstadoError } from '../components/EstadoError'

const ease = [0.23, 1, 0.32, 1]
const PAGE_SIZE = 12
const PREFIJO_ATRIBUTO = 'attr.'
const VISIBLES_POR_FACETA = 6

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
  { value: 'relevancia',     label: 'Más relevantes', soloConTexto: true },
  { value: 'mas_vendidos',   label: 'Más vendidos' },
  { value: 'reciente',       label: 'Más recientes' },
  { value: 'precio_asc',     label: 'Precio: menor a mayor' },
  { value: 'precio_desc',    label: 'Precio: mayor a menor' },
  { value: 'descuento_desc', label: 'Mayor descuento flash' },
]

const GRADIENT = { background: 'linear-gradient(135deg, #29B6F6, #0288D1)' }

// Los filtros viven en la URL: un enlace compartido reproduce la misma búsqueda.
function leerFiltros(searchParams) {
  const atributos = {}
  searchParams.forEach((valor, clave) => {
    if (clave.startsWith(PREFIJO_ATRIBUTO) && valor) {
      const nombre = clave.slice(PREFIJO_ATRIBUTO.length)
      atributos[nombre] = [...(atributos[nombre] || []), valor]
    }
  })
  return {
    q: searchParams.get('q') || '',
    categoria: searchParams.get('categoria') || '',
    orden: searchParams.get('orden') || '',
    flash: searchParams.get('flash') === '1',
    stock: searchParams.get('stock') === '1',
    tiendaya: searchParams.get('tiendaya') === '1',
    pmin: searchParams.get('pmin') || '',
    pmax: searchParams.get('pmax') || '',
    vendedores: searchParams.getAll('vendedor'),
    atributos,
    page: Math.max(1, Number(searchParams.get('page')) || 1),
  }
}

function SectionTitle({ children }) {
  return (
    <p className="font-sans text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--color-text-muted)] mb-2.5">
      {children}
    </p>
  )
}

function Conteo({ valor }) {
  if (valor === undefined || valor === null) return null
  return <span className="font-mono text-[11px] tabular-nums text-[var(--color-text-muted)]">{valor}</span>
}

function Interruptor({ activo, onClick, icono: Icono, etiqueta, conteo, tono = 'azul' }) {
  const colores = tono === 'ambar'
    ? { on: 'border-amber-400 bg-amber-50 text-amber-800 font-semibold', track: 'bg-amber-500', hover: 'hover:border-amber-300' }
    : { on: 'border-[#29B6F6] bg-[#29B6F6]/8 text-[#0277BD] font-semibold', track: 'bg-[#29B6F6]', hover: 'hover:border-[#29B6F6]/40' }
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={activo}
      className={`w-full flex items-center justify-between gap-2 px-3 py-2 rounded-xl border font-sans text-sm transition-all ${
        activo ? colores.on : `border-[var(--color-border)] text-[var(--color-text-secondary)] ${colores.hover}`
      }`}
    >
      <span className="flex items-center gap-2"><Icono size={14} /> {etiqueta}</span>
      <span className="flex items-center gap-2">
        <Conteo valor={conteo} />
        <span className={`w-8 h-4 rounded-full p-0.5 transition-colors ${activo ? colores.track : 'bg-[var(--color-border)]'}`}>
          <span className={`block w-3 h-3 bg-white rounded-full transition-transform ${activo ? 'translate-x-4' : ''}`} />
        </span>
      </span>
    </button>
  )
}

function ListaSeleccion({ opciones, seleccionadas, onToggle }) {
  const [expandida, setExpandida] = useState(false)
  const visibles = expandida ? opciones : opciones.slice(0, VISIBLES_POR_FACETA)
  return (
    <div className="flex flex-col gap-0.5">
      {visibles.map((opcion) => {
        const activa = seleccionadas.includes(opcion.valor)
        return (
          <button
            key={opcion.valor}
            type="button"
            onClick={() => onToggle(opcion.valor)}
            aria-pressed={activa}
            className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg text-left font-sans text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-border)]/60 transition-colors"
          >
            <span className={`h-4 w-4 shrink-0 rounded border flex items-center justify-center transition-colors ${
              activa ? 'border-[#0288D1] bg-[#0288D1] text-white' : 'border-[var(--color-border)]'
            }`}>
              {activa && <Check size={11} strokeWidth={3} />}
            </span>
            <span className={`flex-1 truncate ${activa ? 'text-[var(--color-text-primary)] font-medium' : ''}`}>{opcion.etiqueta || opcion.valor}</span>
            <Conteo valor={opcion.conteo} />
          </button>
        )
      })}
      {opciones.length > VISIBLES_POR_FACETA && (
        <button
          type="button"
          onClick={() => setExpandida((v) => !v)}
          className="self-start px-2 py-1 font-sans text-xs text-[#0288D1] hover:underline"
        >
          {expandida ? 'Ver menos' : `Ver ${opciones.length - VISIBLES_POR_FACETA} más`}
        </button>
      )}
    </div>
  )
}

function FiltrosPrecio({ filtros, rangos, onAplicar }) {
  const [min, setMin] = useState(filtros.pmin)
  const [max, setMax] = useState(filtros.pmax)
  useEffect(() => { setMin(filtros.pmin); setMax(filtros.pmax) }, [filtros.pmin, filtros.pmax])

  return (
    <div>
      <SectionTitle>Precio (GTQ)</SectionTitle>
      {rangos?.length > 0 && (
        <div className="flex flex-col gap-0.5 mb-2.5">
          {rangos.map((rango) => {
            const desde = rango.desde ?? ''
            const hasta = rango.hasta ?? ''
            const activo = String(desde) === filtros.pmin && String(hasta) === filtros.pmax
            return (
              <button
                key={rango.etiqueta}
                type="button"
                onClick={() => (activo ? onAplicar('', '') : onAplicar(String(desde), String(hasta)))}
                aria-pressed={activo}
                className={`flex items-center justify-between px-2 py-1.5 rounded-lg font-sans text-sm transition-colors ${
                  activo ? 'bg-[#29B6F6]/10 text-[#0277BD] font-semibold' : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-border)]/60'
                }`}
              >
                <span>{rango.etiqueta}</span>
                <Conteo valor={rango.conteo} />
              </button>
            )
          })}
        </div>
      )}
      <form
        className="flex gap-2 items-center"
        onSubmit={(e) => { e.preventDefault(); onAplicar(min, max) }}
      >
        <Input type="number" min="0" placeholder="Mín" value={min} onChange={(e) => setMin(e.target.value)} className="text-center" aria-label="Precio mínimo" />
        <span className="text-[var(--color-text-muted)] text-sm font-sans shrink-0">–</span>
        <Input type="number" min="0" placeholder="Máx" value={max} onChange={(e) => setMax(e.target.value)} className="text-center" aria-label="Precio máximo" />
        <button type="submit" className="h-9 px-2.5 shrink-0 rounded-lg font-sans text-xs font-semibold text-white" style={GRADIENT}>
          Ir
        </button>
      </form>
    </div>
  )
}

function FiltersPanel({ filtros, facetas, acciones }) {
  const categorias = facetas?.categorias || []
  const disponibilidad = facetas?.disponibilidad
  const vendedores = facetas?.vendedores || []
  const atributos = facetas?.atributos || []

  return (
    <div className="space-y-5">
      {/* Categorías con conteo de resultados */}
      <div>
        <SectionTitle>Categoría</SectionTitle>
        <div className="flex flex-col gap-0.5">
          <button
            onClick={() => acciones.setCategoria('')}
            className={`flex items-center gap-2.5 text-left px-3 py-2 rounded-xl text-sm font-sans transition-all duration-150 ${
              !filtros.categoria
                ? 'text-white font-semibold shadow-sm'
                : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] hover:text-[var(--color-text-primary)]'
            }`}
            style={!filtros.categoria ? GRADIENT : undefined}
          >
            <Layers size={14} className="shrink-0" />
            Todas las categorías
          </button>
          {categorias.map((cat) => {
            const Icon = ICON_BY_SLUG[cat.valor] || DEFAULT_ICON
            const active = filtros.categoria === cat.valor
            return (
              <button
                key={cat.valor}
                onClick={() => acciones.setCategoria(active ? '' : cat.valor)}
                className={`flex items-center gap-2.5 text-left px-3 py-2 rounded-xl text-sm font-sans transition-all duration-150 ${
                  active
                    ? 'text-white font-semibold shadow-sm'
                    : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] hover:text-[var(--color-text-primary)]'
                }`}
                style={active ? GRADIENT : undefined}
              >
                <Icon size={14} className="shrink-0" strokeWidth={1.5} />
                <span className="flex-1 truncate">{cat.etiqueta}</span>
                <span className={`font-mono text-[11px] tabular-nums ${active ? 'text-white/80' : 'text-[var(--color-text-muted)]'}`}>{cat.conteo}</span>
              </button>
            )
          })}
        </div>
      </div>

      <Separator />

      <div className="space-y-1.5">
        <Interruptor activo={filtros.flash} onClick={() => acciones.toggle('flash')} icono={Zap}
          etiqueta="Ofertas flash" conteo={disponibilidad?.flash} tono="ambar" />
        <Interruptor activo={filtros.stock} onClick={() => acciones.toggle('stock')} icono={PackageCheck}
          etiqueta="Con stock" conteo={disponibilidad?.con_stock} />
        {disponibilidad && (
          <Interruptor activo={filtros.tiendaya} onClick={() => acciones.toggle('tiendaya')} icono={BadgeCheck}
            etiqueta="Vendido por TiendaYa" conteo={disponibilidad.tiendaya} />
        )}
      </div>

      <Separator />

      <FiltrosPrecio filtros={filtros} rangos={facetas?.precio?.rangos} onAplicar={acciones.setPrecio} />

      {vendedores.length > 0 && (
        <>
          <Separator />
          <div>
            <SectionTitle>Vendedor</SectionTitle>
            <ListaSeleccion opciones={vendedores} seleccionadas={filtros.vendedores} onToggle={acciones.toggleVendedor} />
          </div>
        </>
      )}

      {/* Atributos propios de cada categoría (RAM, talla, color...), calculados por el motor */}
      {atributos.map((atributo) => (
        <div key={atributo.nombre}>
          <Separator className="mb-5" />
          <SectionTitle>{atributo.etiqueta}</SectionTitle>
          <ListaSeleccion
            opciones={atributo.valores}
            seleccionadas={filtros.atributos[atributo.nombre] || []}
            onToggle={(valor) => acciones.toggleAtributo(atributo.nombre, valor)}
          />
        </div>
      ))}

      <Separator />

      <button
        onClick={acciones.limpiar}
        className="w-full flex items-center justify-center gap-1.5 py-2 rounded-xl font-sans text-sm text-[var(--color-text-muted)] hover:text-[var(--color-error)] hover:bg-[var(--color-error)]/8 border border-[var(--color-border)] transition-all duration-150"
      >
        <X size={13} /> Limpiar filtros
      </button>
    </div>
  )
}

function Chip({ children, onRemove, tono }) {
  const estilos = tono === 'primario'
    ? { className: 'text-white', style: GRADIENT }
    : tono === 'ambar'
      ? { className: 'bg-amber-100 text-amber-800' }
      : { className: 'bg-[var(--color-border)] text-[var(--color-text-secondary)]' }
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full font-sans text-xs font-semibold ${estilos.className}`} style={estilos.style}>
      {children}
      <button onClick={onRemove} className="hover:opacity-70" aria-label="Quitar filtro"><X size={11} /></button>
    </span>
  )
}

export default function CatalogPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const filtros = leerFiltros(searchParams)
  const [localSearch, setLocalSearch] = useState(filtros.q)

  useEffect(() => { setLocalSearch(filtros.q) }, [filtros.q])

  // Cualquier cambio de filtro vuelve a la primera página.
  function actualizar(mutar, { conservarPagina = false } = {}) {
    const next = new URLSearchParams(searchParams)
    mutar(next)
    if (!conservarPagina) next.delete('page')
    setSearchParams(next)
  }

  function alternarValor(next, clave, valor) {
    const actuales = next.getAll(clave)
    next.delete(clave)
    const nuevos = actuales.includes(valor) ? actuales.filter((v) => v !== valor) : [...actuales, valor]
    nuevos.forEach((v) => next.append(clave, v))
  }

  const acciones = {
    setCategoria: (slug) => actualizar((n) => {
      if (slug) n.set('categoria', slug)
      else n.delete('categoria')
      // Los atributos dependen de la categoría; al cambiarla se reinician.
      ;[...n.keys()].filter((k) => k.startsWith(PREFIJO_ATRIBUTO)).forEach((k) => n.delete(k))
    }),
    toggle: (clave) => actualizar((n) => (n.get(clave) === '1' ? n.delete(clave) : n.set(clave, '1'))),
    setPrecio: (min, max) => actualizar((n) => {
      if (min) n.set('pmin', min); else n.delete('pmin')
      if (max) n.set('pmax', max); else n.delete('pmax')
    }),
    toggleVendedor: (vendedor) => actualizar((n) => alternarValor(n, 'vendedor', vendedor)),
    toggleAtributo: (nombre, valor) => actualizar((n) => alternarValor(n, `${PREFIJO_ATRIBUTO}${nombre}`, valor)),
    setOrden: (orden) => actualizar((n) => n.set('orden', orden)),
    setQ: (q) => actualizar((n) => (q ? n.set('q', q) : n.delete('q'))),
    setPage: (page) => actualizar((n) => n.set('page', String(page)), { conservarPagina: true }),
    limpiar: () => { setLocalSearch(''); setSearchParams({}) },
  }

  function handleSearch(e) {
    e.preventDefault()
    acciones.setQ(localSearch.trim())
  }

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['search', searchParams.toString()],
    queryFn: () => searchProducts({
      q: filtros.q,
      categoria: filtros.categoria,
      orden: filtros.orden,
      solo_flash: filtros.flash,
      solo_stock: filtros.stock,
      solo_tiendaya: filtros.tiendaya,
      precio_min: filtros.pmin,
      precio_max: filtros.pmax,
      vendedores: filtros.vendedores,
      atributos: filtros.atributos,
      page: filtros.page,
      page_size: PAGE_SIZE,
    }).then((r) => r.data),
    placeholderData: keepPreviousData,
  })

  const products = data?.items || []
  // Sin coincidencias el backend devuelve productos populares: no son resultados de la búsqueda.
  const sinCoincidencias = Boolean(data?.sin_coincidencias)
  const totalEncontrados = sinCoincidencias ? 0 : data?.total
  const totalPages = data?.total_pages || 1
  const page = filtros.page
  const facetas = data?.facetas
  const ordenActual = data?.orden || filtros.orden || (filtros.q ? 'relevancia' : 'mas_vendidos')
  const opcionesOrden = SORT_OPTIONS.filter((o) => !o.soloConTexto || filtros.q)

  const activeCategory = facetas?.categorias?.find((c) => c.valor === filtros.categoria)
  const atributosActivos = Object.entries(filtros.atributos).flatMap(([nombre, valores]) =>
    valores.map((valor) => ({
      nombre,
      valor,
      etiqueta: facetas?.atributos?.find((a) => a.nombre === nombre)?.etiqueta || nombre,
    }))
  )
  const hasActiveFilters = Boolean(
    filtros.categoria || filtros.pmin || filtros.pmax || filtros.flash || filtros.stock
    || filtros.tiendaya || filtros.q || filtros.vendedores.length || atributosActivos.length
  )

  function getPageRange() {
    const range = []
    const delta = 2
    for (let i = Math.max(1, page - delta); i <= Math.min(totalPages, page + delta); i++) {
      range.push(i)
    }
    return range
  }

  const titulo = filtros.flash && !filtros.q
    ? 'Ofertas flash'
    : filtros.q ? `"${filtros.q}"` : activeCategory ? activeCategory.etiqueta : 'Catálogo de productos'

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
              {titulo}
            </h1>
            {totalEncontrados !== undefined && (
              <p className="font-sans text-sm text-white/65 mt-1">
                <span className="font-mono tabular-nums font-semibold text-white">{totalEncontrados}</span> producto{totalEncontrados !== 1 ? 's' : ''} encontrado{totalEncontrados !== 1 ? 's' : ''}
                {filtros.q && activeCategory && <> en <span className="font-semibold text-white">{activeCategory.etiqueta}</span></>}
              </p>
            )}
          </motion.div>

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
          className="flex items-center justify-between mb-5 gap-4 flex-wrap"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease, delay: 0.1 }}
        >
          {/* Filtros activos como chips */}
          <div className="flex items-center gap-2 flex-wrap">
            {hasActiveFilters ? (
              <>
                {filtros.categoria && (
                  <Chip tono="primario" onRemove={() => acciones.setCategoria('')}>
                    {activeCategory?.etiqueta || filtros.categoria}
                  </Chip>
                )}
                {filtros.q && <Chip onRemove={() => acciones.setQ('')}>"{filtros.q}"</Chip>}
                {(filtros.pmin || filtros.pmax) && (
                  <Chip onRemove={() => acciones.setPrecio('', '')}>Q{filtros.pmin || '0'} – Q{filtros.pmax || '∞'}</Chip>
                )}
                {filtros.flash && <Chip tono="ambar" onRemove={() => acciones.toggle('flash')}><Zap size={11} fill="currentColor" /> Ofertas flash</Chip>}
                {filtros.stock && <Chip onRemove={() => acciones.toggle('stock')}>Con stock</Chip>}
                {filtros.tiendaya && <Chip onRemove={() => acciones.toggle('tiendaya')}>TiendaYa</Chip>}
                {filtros.vendedores.map((v) => (
                  <Chip key={`v-${v}`} onRemove={() => acciones.toggleVendedor(v)}>{v}</Chip>
                ))}
                {atributosActivos.map((a) => (
                  <Chip key={`a-${a.nombre}-${a.valor}`} onRemove={() => acciones.toggleAtributo(a.nombre, a.valor)}>
                    {a.etiqueta}: {a.valor}
                  </Chip>
                ))}
              </>
            ) : (
              <p className="font-sans text-sm text-[var(--color-text-muted)]">Todos los productos</p>
            )}
          </div>

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

            <div className="w-48 hidden sm:block">
              <Select value={ordenActual} onValueChange={acciones.setOrden}>
                <SelectTrigger aria-label="Ordenar por">
                  <SelectValue placeholder="Ordenar por" />
                </SelectTrigger>
                <SelectContent>
                  {opcionesOrden.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

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
                <div className="p-5 space-y-5">
                  <div className="sm:hidden">
                    <SectionTitle>Ordenar por</SectionTitle>
                    <Select value={ordenActual} onValueChange={acciones.setOrden}>
                      <SelectTrigger><SelectValue placeholder="Ordenar por" /></SelectTrigger>
                      <SelectContent>
                        {opcionesOrden.map((opt) => (
                          <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <FiltersPanel filtros={filtros} facetas={facetas} acciones={acciones} />
                </div>
              </SheetContent>
            </Sheet>
          </div>
        </motion.div>

        {/* ── Avisos del buscador ── */}
        {data?.sugerencia && (
          <div className="mb-4 flex items-center gap-2 font-sans text-sm text-[var(--color-text-secondary)]">
            <Sparkles size={15} className="text-[#29B6F6] shrink-0" />
            ¿Quisiste decir{' '}
            <button
              onClick={() => acciones.setQ(data.sugerencia)}
              className="font-semibold text-[#0288D1] hover:underline"
            >
              {data.sugerencia}
            </button>
            ?
          </div>
        )}
        {sinCoincidencias && (
          <div role="status" className="mb-4 flex items-start gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-2.5 font-sans text-sm text-[var(--color-text-secondary)]">
            <Search size={15} className="mt-0.5 shrink-0 text-[#29B6F6]" />
            <span>
              No encontramos resultados para{' '}
              <span className="font-semibold text-[var(--color-text-primary)]">«{data.consulta}»</span>.
              {data.alternativa === 'populares_con_filtros'
                ? ' Te mostramos productos populares con los filtros que elegiste.'
                : ' Te mostramos productos populares que podrían interesarte.'}
            </span>
          </div>
        )}
        {data?.degradado && (
          <div role="status" className="mb-4 flex items-start gap-2 rounded-xl border border-amber-300 bg-amber-50 px-3.5 py-2.5 font-sans text-sm text-amber-900">
            <AlertTriangle size={15} className="mt-0.5 shrink-0" />
            <span>
              La búsqueda avanzada no está disponible en este momento. Mostramos resultados por coincidencia exacta
              del nombre; algunos filtros no están disponibles.
            </span>
          </div>
        )}

        <div className="flex gap-6">

          {/* ── Sidebar desktop ── */}
          <motion.aside
            className="hidden lg:block w-60 shrink-0"
            initial={{ opacity: 0, x: -16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, ease, delay: 0.12 }}
          >
            <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl p-4 sticky top-24 max-h-[calc(100vh-7rem)] overflow-y-auto">
              <div className="flex items-center justify-between mb-4">
                <span className="font-sans text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--color-text-muted)]">Filtros</span>
                {hasActiveFilters && (
                  <button onClick={acciones.limpiar} className="font-sans text-[11px] text-[#29B6F6] hover:underline">Limpiar</button>
                )}
              </div>
              <FiltersPanel filtros={filtros} facetas={facetas} acciones={acciones} />
            </div>
          </motion.aside>

          {/* ── Grid ── */}
          <div className="flex-1 min-w-0">
            {isError && !isLoading ? (
              // La búsqueda falló (servicio caído, sin conexión): se explica el
              // motivo en lugar de mostrar «Sin resultados».
              <EstadoError compacto error={error} titulo="No pudimos cargar los productos" onReintentar={refetch} />
            ) : isLoading ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-4 lg:gap-5">
                {Array.from({ length: PAGE_SIZE }).map((_, i) => <ProductCardSkeleton key={i} />)}
              </div>
            ) : products.length === 0 ? (
              <motion.div
                className="flex flex-col items-center justify-center py-28 text-center"
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.45, ease }}
              >
                <div className="h-20 w-20 rounded-full flex items-center justify-center mb-5" style={{ backgroundColor: 'rgba(41,182,246,0.08)' }}>
                  <Search size={32} className="text-[#29B6F6]" strokeWidth={1.5} />
                </div>
                <h3 className="font-display font-bold text-xl text-[var(--color-text-primary)] mb-2">Sin resultados</h3>
                <p className="font-sans text-sm text-[var(--color-text-secondary)] mb-6 max-w-xs">
                  {data?.sugerencia
                    ? <>Prueba con <button onClick={() => acciones.setQ(data.sugerencia)} className="font-semibold text-[#0288D1] hover:underline">{data.sugerencia}</button> o con otros filtros.</>
                    : 'No encontramos productos con esos criterios. Prueba con otros filtros.'}
                </p>
                <button
                  onClick={acciones.limpiar}
                  className="flex items-center gap-1.5 px-5 py-2.5 rounded-full font-sans font-semibold text-sm text-white transition-opacity hover:opacity-88"
                  style={GRADIENT}
                >
                  <X size={13} /> Limpiar filtros
                </button>
              </motion.div>
            ) : (
              <div key={`${searchParams.toString()}`} className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-4 lg:gap-5">
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
                  onClick={() => acciones.setPage(page - 1)}
                  aria-label="Página anterior"
                  className="h-9 w-9 flex items-center justify-center rounded-full border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[#29B6F6]/40 hover:text-[#29B6F6] disabled:opacity-40 disabled:pointer-events-none transition-all"
                >
                  <ChevronLeft size={15} />
                </button>

                {page > 3 && (
                  <>
                    <button onClick={() => acciones.setPage(1)} className="h-9 w-9 flex items-center justify-center rounded-full border border-[var(--color-border)] font-mono text-sm text-[var(--color-text-secondary)] hover:border-[#29B6F6]/40 hover:text-[#29B6F6] transition-all">1</button>
                    {page > 4 && <span className="text-[var(--color-text-muted)] text-sm px-1">…</span>}
                  </>
                )}

                {getPageRange().map((p) => (
                  <button
                    key={p}
                    onClick={() => acciones.setPage(p)}
                    aria-current={p === page ? 'page' : undefined}
                    className={p === page
                      ? 'h-9 w-9 flex items-center justify-center rounded-full font-mono text-sm font-semibold text-white transition-all'
                      : 'h-9 w-9 flex items-center justify-center rounded-full font-mono text-sm border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[#29B6F6]/40 hover:text-[#29B6F6] transition-all'}
                    style={p === page ? GRADIENT : undefined}
                  >
                    {p}
                  </button>
                ))}

                {page < totalPages - 2 && (
                  <>
                    {page < totalPages - 3 && <span className="text-[var(--color-text-muted)] text-sm px-1">…</span>}
                    <button onClick={() => acciones.setPage(totalPages)} className="h-9 w-9 flex items-center justify-center rounded-full border border-[var(--color-border)] font-mono text-sm text-[var(--color-text-secondary)] hover:border-[#29B6F6]/40 hover:text-[#29B6F6] transition-all">{totalPages}</button>
                  </>
                )}

                <button
                  disabled={page >= totalPages}
                  onClick={() => acciones.setPage(page + 1)}
                  aria-label="Página siguiente"
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
