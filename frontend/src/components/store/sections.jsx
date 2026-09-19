import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ShoppingBag, Search as SearchIcon, Loader2, ChevronLeft, ChevronRight, X } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { getProducts } from '../../api/products'
import { ProductCard } from '../product/ProductCard'
import { ProductCardSkeleton } from '../ui/skeleton'

// ── Estilos de botón ─────────────────────────────────────────────────────────
function buildButtonStyle(estilo, primary, accent, radius) {
  const base = {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    fontWeight: 700, fontSize: '0.9rem', textDecoration: 'none',
    cursor: 'pointer', width: 'fit-content', marginTop: '1.75rem',
    letterSpacing: '0.01em', transition: 'all .2s ease',
  }
  switch (estilo) {
    case 'degradado':
      return { ...base, background: `linear-gradient(135deg, ${primary}, ${accent})`, color: '#fff', padding: '0.8rem 2rem', borderRadius: `calc(${radius} * 1.5)`, boxShadow: `0 6px 24px ${primary}50` }
    case 'contorno':
      return { ...base, background: 'transparent', border: '2px solid rgba(255,255,255,0.9)', color: '#fff', padding: '0.75rem 2rem', borderRadius: radius, backdropFilter: 'blur(6px)' }
    case 'pildora':
      return { ...base, background: `linear-gradient(135deg, ${primary}, ${accent})`, color: '#fff', padding: '0.85rem 2.5rem', borderRadius: '9999px', boxShadow: `0 8px 32px ${accent}55`, fontSize: '0.95rem' }
    case 'brillo':
      return { ...base, background: 'rgba(255,255,255,0.95)', color: primary, padding: '0.8rem 2rem', borderRadius: radius, boxShadow: '0 8px 32px rgba(255,255,255,0.3)', fontWeight: 800 }
    default: // solido
      return { ...base, background: accent, color: '#fff', padding: '0.75rem 1.75rem', borderRadius: radius }
  }
}

// ── Posición absoluta del logo ────────────────────────────────────────────────
const LOGO_SIZE_MAP = { sm: 36, md: 64, lg: 100, xl: 150 }

function logoAbsoluteStyle(posicion, tamano) {
  const maxH = LOGO_SIZE_MAP[tamano] || 64
  const pad  = '1.25rem'
  const base = { position: 'absolute', maxHeight: `${maxH}px`, maxWidth: `${maxH * 3.5}px`, objectFit: 'contain', filter: 'drop-shadow(0 2px 12px rgba(0,0,0,0.35))', zIndex: 2 }
  const map  = {
    'top-left':   { top: pad, left: pad },
    'top-center': { top: pad, left: '50%', transform: 'translateX(-50%)' },
    'top-right':  { top: pad, right: pad },
    'mid-left':   { top: '50%', left: pad, transform: 'translateY(-50%)' },
    'mid-center': { top: '50%', left: '50%', transform: 'translate(-50%,-50%)' },
    'mid-right':  { top: '50%', right: pad, transform: 'translateY(-50%)' },
    'bot-left':   { bottom: pad, left: pad },
    'bot-center': { bottom: pad, left: '50%', transform: 'translateX(-50%)' },
    'bot-right':  { bottom: pad, right: pad },
  }
  return { ...base, ...(map[posicion] || map['top-left']) }
}

// ── HeroSection ──────────────────────────────────────────────────────────────
export function HeroSection({ config = {}, tema = {} }) {
  const {
    titulo = 'Bienvenido a nuestra tienda',
    subtitulo = '',
    imagen_url = '',
    alineacion = 'center',
    boton_texto = 'Ver productos',
    overlay_opacidad = 40,
    altura = 'md',
  } = config

  const alturas   = { baja: '240px', md: '380px', alta: '520px' }
  const flexAlign = { left: 'flex-start', center: 'center', right: 'flex-end' }
  const textAlign = { left: 'left', center: 'center', right: 'right' }

  const bg = imagen_url
    ? `linear-gradient(rgba(0,0,0,${overlay_opacidad / 100}),rgba(0,0,0,${overlay_opacidad / 100})), url(${imagen_url}) center/cover no-repeat`
    : `linear-gradient(135deg, ${tema.color_primario || '#0288D1'} 0%, ${tema.color_acento || '#f59e0b'} 100%)`

  const titleFont = tema.fuente_titulos ? `'${tema.fuente_titulos}', sans-serif` : 'Inter, sans-serif'
  const bodyFont  = tema.fuente_cuerpo  ? `'${tema.fuente_cuerpo}', sans-serif`  : 'Inter, sans-serif'
  const radius    = { none: '0px', sm: '4px', md: '8px', lg: '16px' }[tema.radio_bordes] || '8px'
  const primary   = tema.color_primario || '#0288D1'
  const accent    = tema.color_acento   || '#f59e0b'
  const estilo    = tema.estilo_boton   || 'degradado'
  const align     = alineacion || 'center'

  const logoStyle = tema.logo_url
    ? logoAbsoluteStyle(tema.logo_posicion || 'top-left', tema.logo_tamano || 'md')
    : null

  // Compatibilidad hacia atrás: si hay boton_texto pero no botones, generamos uno
  const botones = config.botones?.length
    ? config.botones
    : config.boton_texto
      ? [{ id: 'legacy', texto: config.boton_texto, accion: 'productos', url: '', estilo: 'principal' }]
      : []

  function resolveHref(btn) {
    if (btn.accion === 'productos') return '#productos'
    if (btn.accion === 'url' && btn.url) return btn.url
    if (btn.accion === 'catalogo') return '/catalog'
    return '#'
  }

  function resolveTarget(btn) {
    return btn.accion === 'url' && btn.url && (btn.url.startsWith('http://') || btn.url.startsWith('https://'))
      ? '_blank'
      : '_self'
  }

  function resolveStyle(btn) {
    const s = btn.estilo === 'principal' ? estilo : btn.estilo
    return buildButtonStyle(s, primary, accent, radius)
  }

  return (
    <section
      style={{
        position: 'relative', width: '100%', display: 'flex', flexDirection: 'column',
        justifyContent: 'center', alignItems: flexAlign[align] || 'center',
        padding: '3rem 2rem', minHeight: alturas[altura] || alturas.md,
        background: bg, textAlign: textAlign[align] || 'center', overflow: 'hidden',
      }}
    >
      {/* Logo absolutamente posicionado */}
      {tema.logo_url && logoStyle && (
        <img src={tema.logo_url} alt="Logo" style={logoStyle} />
      )}

      {/* Contenido */}
      <div style={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', alignItems: flexAlign[align] || 'center', width: '100%' }}>
        {titulo && (
          <h2 style={{
            fontFamily: titleFont, fontSize: 'clamp(1.7rem, 4.5vw, 3.2rem)',
            lineHeight: 1.12, maxWidth: '760px', fontWeight: 800, color: '#fff',
            textShadow: '0 2px 8px rgba(0,0,0,0.25)', letterSpacing: '-0.01em',
          }}>
            {titulo}
          </h2>
        )}
        {subtitulo && (
          <p style={{
            fontFamily: bodyFont, marginTop: '0.85rem', maxWidth: '38rem',
            fontSize: 'clamp(1rem, 2vw, 1.2rem)', color: 'rgba(255,255,255,0.88)',
            lineHeight: 1.6,
          }}>
            {subtitulo}
          </p>
        )}

        {/* Fila de botones */}
        {botones.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginTop: '1.75rem', justifyContent: flexAlign[align] || 'center' }}>
            {botones.map(btn => (
              <a
                key={btn.id}
                href={resolveHref(btn)}
                target={resolveTarget(btn)}
                rel={resolveTarget(btn) === '_blank' ? 'noopener noreferrer' : undefined}
                style={{ ...resolveStyle(btn), marginTop: 0 }}
                onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.filter = 'brightness(1.08)' }}
                onMouseLeave={e => { e.currentTarget.style.transform = ''; e.currentTarget.style.filter = '' }}
              >
                {btn.texto}
              </a>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

// ── TextSection ───────────────────────────────────────────────────────────────
export function TextSection({ config = {}, tema = {} }) {
  const { titulo = '', contenido = '', alineacion = 'center', tamano = 'md' } = config
  const fontSizes = { sm: '0.875rem', md: '1rem', lg: '1.125rem' }
  const aligns = { left: { textAlign: 'left' }, center: { textAlign: 'center', marginLeft: 'auto', marginRight: 'auto' }, right: { textAlign: 'right', marginLeft: 'auto' } }

  const titleFont = tema.fuente_titulos ? `'${tema.fuente_titulos}', sans-serif` : 'var(--store-font-title, Inter, sans-serif)'
  const bodyFont  = tema.fuente_cuerpo  ? `'${tema.fuente_cuerpo}', sans-serif`  : 'var(--store-font-body, Inter, sans-serif)'
  const textColor = tema.color_texto    || '#1a1a1a'
  const primary   = tema.color_primario || '#0288D1'

  if (!titulo && !contenido) return null
  return (
    <section style={{ width: '100%', padding: '3rem 1.5rem' }}>
      <div style={{ maxWidth: '48rem', ...aligns[alineacion] }}>
        {titulo && (
          <h2 style={{ fontFamily: titleFont, fontWeight: 700, marginBottom: '1rem', fontSize: 'clamp(1.3rem, 3vw, 2rem)', color: primary }}>
            {titulo}
          </h2>
        )}
        {contenido && (
          <p style={{ fontFamily: bodyFont, lineHeight: 1.7, fontSize: fontSizes[tamano] || fontSizes.md, color: textColor, opacity: 0.85, whiteSpace: 'pre-wrap' }}>
            {contenido}
          </p>
        )}
      </div>
    </section>
  )
}

// ── ProductsSection ───────────────────────────────────────────────────────────
export function ProductsSection({ config = {}, tema = {}, vendedorId }) {
  const { titulo = 'Nuestros productos', cantidad = 8 } = config
  const [page, setPage] = useState(1)
  const [searchParams] = useSearchParams()
  const q = searchParams.get('q') || ''

  // Vuelve a página 1 si cambia la cantidad o la búsqueda
  useEffect(() => { setPage(1) }, [cantidad, q])

  const titleFont = tema.fuente_titulos ? `'${tema.fuente_titulos}', sans-serif` : 'var(--store-font-title, Inter, sans-serif)'
  const bodyFont  = tema.fuente_cuerpo  ? `'${tema.fuente_cuerpo}', sans-serif`  : 'var(--store-font-body, Inter, sans-serif)'
  const primary   = tema.color_primario || '#0288D1'

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['store-section-products', vendedorId, cantidad, page, q],
    queryFn: () => getProducts({ vendedor_id: vendedorId, page, page_size: cantidad, disponible: true, ...(q && { q }) }).then(r => r.data),
    enabled: Boolean(vendedorId),
    staleTime: 60_000,
    keepPreviousData: true,
  })

  const items      = data?.items || []
  const totalPages = data?.total_pages || 1

  const navBtnStyle = (disabled) => ({
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    width: '2.5rem', height: '2.5rem', borderRadius: '50%',
    border: `2px solid ${disabled ? '#e5e7eb' : primary}`,
    background: disabled ? 'transparent' : primary,
    color: disabled ? '#d1d5db' : '#fff',
    cursor: disabled ? 'not-allowed' : 'pointer',
    transition: 'all .15s',
    opacity: disabled ? 0.5 : 1,
  })

  return (
    <section id="productos" style={{ width: '100%', padding: '3rem 1.5rem' }}>
      <div style={{ maxWidth: '72rem', margin: '0 auto' }}>
        {titulo && (
          <h2 style={{ fontFamily: titleFont, fontWeight: 700, marginBottom: '2rem', textAlign: 'center', fontSize: 'clamp(1.3rem, 3vw, 2rem)', color: primary }}>
            {titulo}
          </h2>
        )}

        {isLoading ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {Array.from({ length: Math.min(cantidad, 4) }).map((_, i) => <ProductCardSkeleton key={i} />)}
          </div>
        ) : items.length > 0 ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4"
              style={{ opacity: isFetching ? 0.6 : 1, transition: 'opacity .2s' }}>
              {items.map(p => <ProductCard key={p._id} product={p} vendedorId={vendedorId} />)}
            </div>

            {totalPages > 1 && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '1rem', marginTop: '2.5rem' }}>
                <button
                  disabled={page <= 1 || isFetching}
                  onClick={() => setPage(p => p - 1)}
                  style={navBtnStyle(page <= 1 || isFetching)}
                  onMouseEnter={e => { if (page > 1) e.currentTarget.style.filter = 'brightness(1.1)' }}
                  onMouseLeave={e => { e.currentTarget.style.filter = '' }}
                >
                  <ChevronLeft size={18} />
                </button>

                <span style={{ fontFamily: bodyFont, fontSize: '0.875rem', color: primary, fontWeight: 600 }}>
                  {page} / {totalPages}
                </span>

                <button
                  disabled={page >= totalPages || isFetching}
                  onClick={() => setPage(p => p + 1)}
                  style={navBtnStyle(page >= totalPages || isFetching)}
                  onMouseEnter={e => { if (page < totalPages) e.currentTarget.style.filter = 'brightness(1.1)' }}
                  onMouseLeave={e => { e.currentTarget.style.filter = '' }}
                >
                  <ChevronRight size={18} />
                </button>
              </div>
            )}
          </>
        ) : (
          <div style={{ textAlign: 'center', padding: '4rem 0', opacity: 0.5 }}>
            <ShoppingBag size={40} style={{ margin: '0 auto 0.75rem' }} strokeWidth={1.5} />
            <p style={{ fontFamily: titleFont, fontSize: '0.875rem' }}>
              {q ? `Sin resultados para "${q}"` : 'Sin productos disponibles.'}
            </p>
          </div>
        )}
      </div>
    </section>
  )
}

// ── BuscadorSection ───────────────────────────────────────────────────────────
export function BuscadorSection({ config = {}, tema = {} }) {
  const { placeholder = 'Buscar en nuestra tienda…', estilo = 'redondeado' } = config
  const [searchParams, setSearchParams] = useSearchParams()
  const activeQ = searchParams.get('q') || ''
  const [q, setQ] = useState(activeQ)

  // Sincroniza el input si alguien limpia la búsqueda desde fuera
  useEffect(() => { setQ(activeQ) }, [activeQ])

  const primary  = tema.color_primario || '#0288D1'
  const accent   = tema.color_acento   || '#f59e0b'
  const bodyFont = tema.fuente_cuerpo  ? `'${tema.fuente_cuerpo}', sans-serif` : 'Inter, sans-serif'
  const radius   = { none: '0px', sm: '4px', md: '8px', lg: '16px' }[tema.radio_bordes] || '8px'

  function handleSearch(e) {
    e.preventDefault()
    const term = q.trim()
    setSearchParams(term ? { q: term } : {}, { replace: true })
  }

  function handleClear() {
    setQ('')
    setSearchParams({}, { replace: true })
  }

  const inputStyles = {
    minimalista: {
      wrapper: { borderBottom: `2px solid ${primary}`, borderRadius: 0, background: 'transparent', padding: '0.5rem 0' },
      input:   { background: 'transparent', border: 'none', outline: 'none', color: 'inherit' },
    },
    cuadrado: {
      wrapper: { border: `2px solid ${primary}`, borderRadius: radius, background: '#fff', padding: '0.5rem 1rem' },
      input:   { background: 'transparent', border: 'none', outline: 'none' },
    },
    redondeado: {
      wrapper: { border: `2px solid ${primary}`, borderRadius: '9999px', background: '#fff', padding: '0.6rem 1.25rem' },
      input:   { background: 'transparent', border: 'none', outline: 'none' },
    },
    con_boton: {
      wrapper: { border: `2px solid ${primary}`, borderRadius: radius, background: '#fff', padding: '0.25rem 0.25rem 0.25rem 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' },
      input:   { background: 'transparent', border: 'none', outline: 'none', flex: 1 },
    },
  }

  const s = inputStyles[estilo] || inputStyles.redondeado

  return (
    <section style={{ width: '100%', padding: '2.5rem 1.5rem' }}>
      <div style={{ maxWidth: '42rem', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        <form onSubmit={handleSearch}>
          <div style={{ display: 'flex', alignItems: 'center', gap: estilo === 'con_boton' ? 0 : '0.75rem', ...s.wrapper }}>
            {estilo !== 'con_boton' && (
              <SearchIcon size={18} style={{ color: primary, flexShrink: 0 }} />
            )}
            <input
              type="text"
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder={placeholder}
              style={{
                ...s.input,
                flex: 1,
                fontFamily: bodyFont,
                fontSize: '1rem',
                color: 'var(--store-text, #1a1a1a)',
                width: '100%',
              }}
            />
            {/* Botón limpiar cuando hay búsqueda activa */}
            {activeQ && estilo !== 'con_boton' && (
              <button type="button" onClick={handleClear}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: primary, flexShrink: 0, padding: '0.25rem', display: 'flex' }}>
                <X size={16} />
              </button>
            )}
            {estilo === 'con_boton' && (
              <button
                type="submit"
                style={{
                  ...buildButtonStyle('degradado', primary, accent, radius),
                  marginTop: 0,
                  padding: '0.6rem 1.25rem',
                  fontFamily: bodyFont,
                  fontSize: '0.875rem',
                  flexShrink: 0,
                }}
              >
                <SearchIcon size={15} /> Buscar
              </button>
            )}
          </div>
        </form>

        {/* Indicador de búsqueda activa */}
        {activeQ && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontFamily: bodyFont, fontSize: '0.8rem', color: primary }}>
            <SearchIcon size={13} />
            <span>Resultados para <strong>"{activeQ}"</strong></span>
            <button onClick={handleClear}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: primary, display: 'inline-flex', alignItems: 'center', gap: '0.2rem', fontFamily: bodyFont, fontSize: '0.8rem', padding: 0, textDecoration: 'underline' }}>
              <X size={12} /> Limpiar
            </button>
          </div>
        )}
      </div>
    </section>
  )
}

// ── SeparadorSection ──────────────────────────────────────────────────────────
export function SeparadorSection({ config = {} }) {
  const { estilo = 'linea', alto = 'md' } = config
  const altos = { bajo: '24px', md: '56px', alto: '96px' }
  if (estilo === 'espacio') return <div style={{ height: altos[alto] || altos.md }} />
  return (
    <div style={{ padding: `${parseInt(altos[alto] || 56) / 2}px 1.5rem` }}>
      <hr style={{ border: 'none', borderTop: '1px solid var(--store-primary, #0288D1)', opacity: 0.2, maxWidth: '600px', margin: '0 auto' }} />
    </div>
  )
}
