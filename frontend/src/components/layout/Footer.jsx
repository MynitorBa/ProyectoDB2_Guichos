import { Link } from 'react-router-dom'
import { ShoppingBag, Store, LogIn, MapPin, Mail } from 'lucide-react'

export function Footer() {
  const year = new Date().getFullYear()
  return (
    <footer className="relative overflow-hidden bg-white border-t border-[var(--color-border)]">

      {/* Textura sutil de luz */}
      <div
        className="absolute inset-0 pointer-events-none opacity-[0.04]"
        style={{ backgroundImage: 'radial-gradient(ellipse at 80% 0%, #29B6F6 0%, transparent 55%)' }}
      />

      <div className="relative max-w-[1320px] mx-auto px-6 lg:px-12 pt-12 pb-8">

        {/* Cuerpo principal — 3 columnas */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-10 mb-10">

          {/* Columna 1 — Marca */}
          <div className="flex flex-col gap-4">
            <img src="/TiendaYAlogo.png" alt="TiendaYa" className="h-12 w-auto object-contain self-start drop-shadow-md" />
            <p className="font-sans text-sm text-[var(--color-text-secondary)] leading-relaxed max-w-[220px]">
              El marketplace guatemalteco donde comprar y vender es simple.
            </p>
            <div className="flex items-center gap-1.5 text-[var(--color-text-muted)]">
              <MapPin size={13} className="shrink-0" />
              <span className="font-sans text-xs">Guatemala, C.A.</span>
            </div>
            <div className="flex items-center gap-1.5 text-[var(--color-text-muted)]">
              <Mail size={13} className="shrink-0" />
              <span className="font-sans text-xs">contacto@tiendaya.gt</span>
            </div>
          </div>

          {/* Columna 2 — Navegación */}
          <div className="flex flex-col gap-3">
            <p className="font-display font-semibold text-xs uppercase tracking-[0.15em] text-[var(--color-text-muted)] mb-1">
              Explorar
            </p>
            <Link
              to="/catalog"
              className="flex items-center gap-2 font-sans text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors duration-150"
            >
              <ShoppingBag size={14} className="shrink-0 text-[#29B6F6]" />
              Catálogo de productos
            </Link>
            <Link
              to="/register"
              className="flex items-center gap-2 font-sans text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors duration-150"
            >
              <Store size={14} className="shrink-0 text-[#29B6F6]" />
              Empezar a vender
            </Link>
            <Link
              to="/login"
              className="flex items-center gap-2 font-sans text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors duration-150"
            >
              <LogIn size={14} className="shrink-0 text-[#29B6F6]" />
              Iniciar sesión
            </Link>
          </div>

          {/* Columna 3 — Vendedores CTA mini */}
          <div className="flex flex-col justify-center">
            <div
              className="rounded-2xl p-5 flex flex-col gap-3"
              style={{ backgroundColor: '#29B6F6' }}
            >
              <p className="font-display font-bold text-white text-base leading-snug">
                ¿Listo para vender?
              </p>
              <p className="font-sans text-xs text-white/75 leading-relaxed">
                Crea tu cuenta gratis y publica tu primer producto en minutos.
              </p>
              <Link
                to="/register"
                className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-white font-sans font-semibold text-sm py-2 px-4 transition-all duration-200 hover:bg-white/90 hover:shadow-md active:scale-95"
                style={{ color: '#29B6F6' }}
              >
                Comenzar gratis
              </Link>
            </div>
          </div>

        </div>

        {/* Separador */}
        <div className="border-t border-[var(--color-border)] pt-5 flex flex-col sm:flex-row items-center justify-between gap-2">
          <span className="font-sans text-xs text-[var(--color-text-muted)]">
            © {year} TiendaYa · Proyecto UNIS — Bases de Datos 2
          </span>
          <span className="font-sans text-xs text-[var(--color-text-muted)]">
            Hecho con dedicación en Guatemala
          </span>
        </div>

      </div>
    </footer>
  )
}
