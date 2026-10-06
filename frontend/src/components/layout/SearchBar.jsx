import { useEffect, useId, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Search, Layers, CornerDownLeft, Loader2 } from 'lucide-react'
import { suggestProducts } from '../../api/search'
import { ProductImage } from '../product/ProductImage'
import { cn, formatQ } from '../../lib/utils'

function useDebounced(value, delay) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay)
    return () => window.clearTimeout(timer)
  }, [value, delay])
  return debounced
}

// Buscador del encabezado con autocompletado (Elasticsearch completion suggester).
// Tolera errores al escribir ("licuadroa") y encuentra palabras que no son la
// primera del nombre ("galax" → Samsung Galaxy). Navegable con teclado.
export function SearchBar({ className, onSearch }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const navigate = useNavigate()
  const listId = useId()
  const inputRef = useRef(null)
  const term = useDebounced(q.trim(), 200)

  const { data, isFetching } = useQuery({
    queryKey: ['search-suggest', term],
    queryFn: () => suggestProducts(term).then((r) => r.data),
    enabled: term.length >= 2,
    staleTime: 30_000,
  })

  const productos = term.length >= 2 ? data?.productos || [] : []
  const categorias = term.length >= 2 ? data?.categorias || [] : []
  const opciones = [
    ...(q.trim() ? [{ tipo: 'buscar', key: 'buscar' }] : []),
    ...categorias.map((c) => ({ tipo: 'categoria', key: `c-${c.slug}`, ...c })),
    ...productos.map((p) => ({ tipo: 'producto', key: `p-${p.producto_id}`, ...p })),
  ]

  useEffect(() => { setActive(-1) }, [term])

  function cerrar() {
    setOpen(false)
    setActive(-1)
  }

  function elegir(opcion) {
    const texto = q.trim()
    if (!opcion || opcion.tipo === 'buscar') {
      if (!texto) return
      navigate(`/catalog?q=${encodeURIComponent(texto)}`)
    } else if (opcion.tipo === 'categoria') {
      navigate(`/catalog?categoria=${encodeURIComponent(opcion.slug)}`)
    } else {
      navigate(`/products/${opcion.producto_id}`)
    }
    cerrar()
    inputRef.current?.blur()
    onSearch?.()
  }

  function onKeyDown(e) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setOpen(true)
      setActive((i) => (opciones.length ? (i + 1) % opciones.length : -1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => (opciones.length ? (i <= 0 ? opciones.length - 1 : i - 1) : -1))
    } else if (e.key === 'Escape') {
      cerrar()
    } else if (e.key === 'Enter') {
      e.preventDefault()
      elegir(active >= 0 ? opciones[active] : null)
    }
  }

  const mostrarLista = open && q.trim().length >= 2 && opciones.length > 0
  const sinCoincidencias = open && term.length >= 2 && !isFetching && data && !productos.length && !categorias.length

  return (
    <div className={cn('relative flex items-center', className)}>
      <Search
        size={15}
        className={cn(
          'absolute left-3.5 pointer-events-none transition-colors duration-150',
          open ? 'text-[#29B6F6]' : 'text-[var(--color-text-muted)]'
        )}
      />
      <input
        ref={inputRef}
        value={q}
        onChange={(e) => { setQ(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onBlur={cerrar}
        onKeyDown={onKeyDown}
        placeholder="Buscar productos..."
        role="combobox"
        aria-expanded={mostrarLista}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
        className="w-full h-10 pl-9 pr-9 bg-[var(--color-background)] border border-[var(--color-border)] rounded-full font-sans text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[#29B6F6] focus:ring-2 focus:ring-[#29B6F6]/20 transition-all duration-200"
      />
      {isFetching && term.length >= 2 && (
        <Loader2 size={14} className="absolute right-3.5 animate-spin text-[var(--color-text-muted)]" />
      )}

      {(mostrarLista || sinCoincidencias) && (
        <ul
          id={listId}
          role="listbox"
          // mousedown antes del blur del input, para que el clic llegue a la opción
          onMouseDown={(e) => e.preventDefault()}
          className="absolute top-full left-0 right-0 mt-2 z-50 max-h-[70vh] overflow-y-auto bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl shadow-[0_16px_40px_rgba(0,0,0,0.14)] py-1.5"
        >
          {opciones.map((opcion, i) => {
            const activa = i === active
            const base = cn(
              'flex items-center gap-3 px-3.5 py-2 cursor-pointer font-sans text-sm',
              activa ? 'bg-[#29B6F6]/10' : 'hover:bg-[var(--color-background)]'
            )
            const encabezado = (titulo) => (
              <p className="px-3.5 pt-2 pb-1 font-sans text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--color-text-muted)]">
                {titulo}
              </p>
            )
            if (opcion.tipo === 'buscar') {
              return (
                <li key={opcion.key} id={`${listId}-${i}`} role="option" aria-selected={activa}
                  className={base} onClick={() => elegir(opcion)} onMouseEnter={() => setActive(i)}>
                  <Search size={14} className="text-[#29B6F6] shrink-0" />
                  <span className="flex-1 truncate text-[var(--color-text-primary)]">
                    Buscar <span className="font-semibold">“{q.trim()}”</span>
                  </span>
                  <CornerDownLeft size={12} className="text-[var(--color-text-muted)]" />
                </li>
              )
            }
            const primeraDeTipo = opciones.findIndex((o) => o.tipo === opcion.tipo) === i
            if (opcion.tipo === 'categoria') {
              return (
                <li key={opcion.key} role="presentation">
                  {primeraDeTipo && encabezado('Categorías')}
                  <div id={`${listId}-${i}`} role="option" aria-selected={activa}
                    className={base} onClick={() => elegir(opcion)} onMouseEnter={() => setActive(i)}>
                    <Layers size={14} className="text-[var(--color-text-muted)] shrink-0" />
                    <span className="text-[var(--color-text-primary)]">{opcion.nombre}</span>
                  </div>
                </li>
              )
            }
            return (
              <li key={opcion.key} role="presentation">
                {primeraDeTipo && encabezado('Productos')}
                <div id={`${listId}-${i}`} role="option" aria-selected={activa}
                  className={base} onClick={() => elegir(opcion)} onMouseEnter={() => setActive(i)}>
                  <div className="h-9 w-9 shrink-0 rounded-lg overflow-hidden bg-[var(--color-background)]">
                    <ProductImage src={opcion.imagen} alt={opcion.nombre} nombre={opcion.nombre} aspectRatio="aspect-square" />
                  </div>
                  <span className="flex-1 min-w-0 truncate text-[var(--color-text-primary)]">{opcion.nombre}</span>
                  {opcion.precio != null && (
                    <span className="font-mono text-xs tabular-nums text-[#0277BD] shrink-0">{formatQ(opcion.precio)}</span>
                  )}
                </div>
              </li>
            )
          })}
          {sinCoincidencias && (
            <li className="px-3.5 py-2 font-sans text-xs text-[var(--color-text-muted)]">
              Sin sugerencias. Presiona Enter para buscar igualmente.
            </li>
          )}
          {data?.degradado && (
            <li className="px-3.5 pt-1 pb-1.5 font-sans text-[11px] text-[var(--color-text-muted)]">
              Sugerencias simplificadas temporalmente.
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
