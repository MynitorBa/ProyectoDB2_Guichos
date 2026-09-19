import { useEffect } from 'react'
import { HeroSection, TextSection, ProductsSection, BuscadorSection, SeparadorSection } from './sections'

const GOOGLE_FONTS = ['Playfair Display', 'Lora', 'Raleway', 'Montserrat', 'Poppins', 'Merriweather', 'Nunito', 'DM Sans']
const RADIUS = { none: '0px', sm: '4px', md: '8px', lg: '16px' }

function loadGoogleFont(name) {
  const id = `gf-${name.replace(/\s+/g, '-').toLowerCase()}`
  if (document.getElementById(id)) return
  const link = document.createElement('link')
  link.id = id
  link.rel = 'stylesheet'
  link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(name)}:wght@400;600;700&display=swap`
  document.head.appendChild(link)
}

const SECTION_MAP = {
  hero:       HeroSection,
  texto:      TextSection,
  productos:  ProductsSection,
  buscador:   BuscadorSection,
  separador:  SeparadorSection,
}

export default function StoreRenderer({ config = {}, vendedorId, className = '' }) {
  const tema = config.tema || {}
  const secciones = config.secciones || []

  useEffect(() => {
    [tema.fuente_titulos, tema.fuente_cuerpo].forEach(f => {
      if (f && GOOGLE_FONTS.includes(f)) loadGoogleFont(f)
    })
  }, [tema.fuente_titulos, tema.fuente_cuerpo])

  const bodyFont  = tema.fuente_cuerpo  ? `'${tema.fuente_cuerpo}', sans-serif`  : 'Inter, sans-serif'
  const titleFont = tema.fuente_titulos ? `'${tema.fuente_titulos}', sans-serif` : 'Inter, sans-serif'

  const cssVars = {
    '--store-primary':    tema.color_primario || '#0288D1',
    '--store-bg':         tema.color_fondo    || '#ffffff',
    '--store-text':       tema.color_texto    || '#1a1a1a',
    '--store-accent':     tema.color_acento   || '#f59e0b',
    '--store-radius':     RADIUS[tema.radio_bordes] || RADIUS.md,
    '--store-font-body':  bodyFont,
    '--store-font-title': titleFont,
    backgroundColor:      tema.color_fondo    || '#ffffff',
    color:                tema.color_texto    || '#1a1a1a',
    fontFamily:           bodyFont,
  }

  const visibles = secciones.filter(s => s.visible !== false)

  return (
    <div style={cssVars} className={`min-h-screen ${className}`}>
      {visibles.map(seccion => {
        const Comp = SECTION_MAP[seccion.tipo]
        if (!Comp) return null
        return (
          <Comp
            key={seccion.id}
            config={seccion.config || {}}
            tema={tema}
            vendedorId={vendedorId}
          />
        )
      })}
      {visibles.length === 0 && (
        <div className="flex items-center justify-center min-h-[400px] opacity-30">
          <p className="font-sans text-sm">Agrega secciones desde el editor.</p>
        </div>
      )}
    </div>
  )
}
