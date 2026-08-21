import { useState, useEffect, useRef } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import {
  Search, ShoppingCart, User, ChevronDown, Menu, X,
  LogOut, Package, Settings, Sun, Moon,
  Monitor, Smartphone, Headphones, Shirt, Layers, ShoppingBag,
  BookOpen, Apple, Home, Dumbbell, Wrench, Gamepad2,
} from 'lucide-react'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import { Sheet, SheetTrigger, SheetContent } from '../ui/sheet'
import { useAuth } from '../../context/AuthContext'
import { useCart } from '../../context/CartContext'
import { cn } from '../../lib/utils'

const CATEGORIES = [
  { slug: 'computadoras', label: 'Computadoras', Icon: Monitor     },
  { slug: 'celulares',    label: 'Celulares',    Icon: Smartphone  },
  { slug: 'audio',        label: 'Audio',        Icon: Headphones  },
  { slug: 'camisas',      label: 'Camisas',      Icon: Shirt       },
  { slug: 'pantalones',   label: 'Pantalones',   Icon: Layers      },
  { slug: 'calzado',      label: 'Calzado',      Icon: ShoppingBag },
  { slug: 'libros',       label: 'Libros',       Icon: BookOpen    },
  { slug: 'alimentos',    label: 'Alimentos',    Icon: Apple       },
  { slug: 'hogar',        label: 'Hogar',        Icon: Home        },
  { slug: 'deportes',     label: 'Deportes',     Icon: Dumbbell    },
  { slug: 'herramientas', label: 'Herramientas', Icon: Wrench      },
  { slug: 'juguetes',     label: 'Juguetes',     Icon: Gamepad2    },
]

function Logo() {
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" className="shrink-0" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="var(--color-action)" />
      {/* shopping bag */}
      <path d="M10 14h12l-1.8 9H11.8L10 14z" stroke="white" strokeWidth="1.5" strokeLinejoin="round" fill="none" />
      <path d="M13 14c0-1.657 1.343-3 3-3s3 1.343 3 3" stroke="white" strokeWidth="1.5" strokeLinecap="round" fill="none" />
      {/* checkmark */}
      <path d="M13.5 19.5l1.5 1.5 3.5-3.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function SearchBar({ className, onSearch }) {
  const [q, setQ] = useState('')
  const navigate = useNavigate()
  function submit(e) {
    e.preventDefault()
    if (q.trim()) { navigate(`/catalog?q=${encodeURIComponent(q.trim())}`); onSearch?.() }
  }
  return (
    <form onSubmit={submit} className={cn('relative flex items-center', className)}>
      <Search size={15} className="absolute left-3 text-[var(--color-text-muted)] pointer-events-none" />
      <input
        value={q}
        onChange={e => setQ(e.target.value)}
        placeholder="Buscar productos..."
        className="w-full h-10 pl-9 pr-4 bg-[var(--color-background)] border border-[var(--color-border)] rounded-[var(--radius-md)] font-sans text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-action)] focus:ring-2 focus:ring-[var(--color-action)]/20 transition-colors"
      />
    </form>
  )
}

function CartIcon() {
  const { cart } = useCart()
  const count = cart?.items?.length || 0
  return (
    <Link
      to="/cart"
      className="relative p-2 rounded-[var(--radius-md)] text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] hover:text-[var(--color-text-primary)] transition-colors"
      aria-label={`Carrito, ${count} artículos`}
    >
      <ShoppingCart size={20} />
      {count > 0 && (
        <span className="absolute -top-0.5 -right-0.5 h-5 min-w-[20px] px-1 flex items-center justify-center rounded-full bg-[var(--color-action)] text-white font-sans font-bold text-[10px] leading-none">
          {count > 99 ? '99+' : count}
        </span>
      )}
    </Link>
  )
}

function UserMenu({ user, signOut }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    function handler(e) { if (!ref.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  if (!user) {
    return (
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" asChild><Link to="/login">Entrar</Link></Button>
        <Button variant="primary" size="sm" asChild><Link to="/register">Registrarse</Link></Button>
      </div>
    )
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 p-1.5 rounded-[var(--radius-md)] hover:bg-[var(--color-border)] transition-colors"
      >
        <div className="h-8 w-8 rounded-full bg-[var(--color-action)]/10 flex items-center justify-center">
          <span className="font-display font-semibold text-sm text-[var(--color-action)]">
            {user.nombre?.[0]?.toUpperCase() || 'U'}
          </span>
        </div>
        <ChevronDown size={12} className={cn('text-[var(--color-text-muted)] transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1.5 w-48 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] shadow-[var(--shadow-lg)] py-1 z-50">
          <div className="px-3 py-2 border-b border-[var(--color-border)]">
            <p className="font-display font-semibold text-sm text-[var(--color-text-primary)] truncate">{user.nombre} {user.apellido}</p>
            <p className="font-sans text-xs text-[var(--color-text-muted)] truncate">{user.email}</p>
          </div>
          <Link to="/orders" onClick={() => setOpen(false)} className="flex items-center gap-2.5 px-3 py-2 font-sans text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-background)] hover:text-[var(--color-text-primary)] transition-colors">
            <Package size={14} /> Mis pedidos
          </Link>
          {user.roles?.includes('administrador') && (
            <Link to="/admin" onClick={() => setOpen(false)} className="flex items-center gap-2.5 px-3 py-2 font-sans text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-background)] hover:text-[var(--color-text-primary)] transition-colors">
              <Settings size={14} /> Panel admin
            </Link>
          )}
          <div className="border-t border-[var(--color-border)] mt-1 pt-1">
            <button onClick={() => { signOut(); setOpen(false) }} className="flex w-full items-center gap-2.5 px-3 py-2 font-sans text-sm text-[var(--color-error)] hover:bg-[var(--color-error-light)] transition-colors">
              <LogOut size={14} /> Cerrar sesión
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function CategoryDropdown() {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const navigate = useNavigate()
  useEffect(() => {
    function handler(e) { if (!ref.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-3 h-9 rounded-[var(--radius-md)] font-display font-semibold text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] hover:text-[var(--color-text-primary)] transition-colors"
      >
        <Menu size={15} />
        Todas las categorías
        <ChevronDown size={12} className={cn('transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="absolute left-0 top-full mt-1.5 w-72 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] shadow-[var(--shadow-lg)] py-2 z-50 grid grid-cols-2 gap-0.5">
          {CATEGORIES.map(cat => {
            const { Icon } = cat
            return (
              <button
                key={cat.slug}
                onClick={() => { navigate(`/catalog?categoria=${cat.slug}`); setOpen(false) }}
                className="flex items-center gap-2 px-3 py-2 font-sans text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-background)] hover:text-[var(--color-text-primary)] transition-colors rounded-[var(--radius-md)] mx-1"
              >
                <Icon size={15} className="text-[var(--color-action)] shrink-0" strokeWidth={1.5} />
                {cat.label}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

export function Header() {
  const { user, signOut } = useAuth()
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'))
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()

  useEffect(() => { setMobileOpen(false) }, [location])

  function toggleDark() {
    document.documentElement.classList.toggle('dark')
    setDark(d => !d)
  }

  return (
    <header className="sticky top-0 z-40 bg-[var(--color-surface)]/95 backdrop-blur-sm border-b border-[var(--color-border)]">
      {/* ── Barra principal ── */}
      <div className="max-w-[1280px] mx-auto px-4 md:px-6 h-16 flex items-center gap-4">
        {/* Logo */}
        <Link to="/" className="shrink-0 flex items-center gap-2 group">
          <Logo />
          <span className="font-display font-bold text-lg text-[var(--color-text-primary)] hidden sm:block">
            TiendaYa
          </span>
        </Link>

        {/* Buscador — desktop */}
        <SearchBar className="flex-1 hidden md:flex max-w-xl" />

        {/* Acciones */}
        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={toggleDark}
            className="p-2 rounded-[var(--radius-md)] text-[var(--color-text-muted)] hover:bg-[var(--color-border)] hover:text-[var(--color-text-primary)] transition-colors"
            aria-label="Cambiar tema"
          >
            {dark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <CartIcon />
          <UserMenu user={user} signOut={signOut} />

          {/* Menú móvil */}
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger asChild>
              <button className="md:hidden p-2 rounded-[var(--radius-md)] text-[var(--color-text-muted)] hover:bg-[var(--color-border)]">
                <Menu size={20} />
              </button>
            </SheetTrigger>
            <SheetContent side="right" title="Menú">
              <div className="px-5 py-4 space-y-4">
                <SearchBar onSearch={() => setMobileOpen(false)} />
                <nav className="space-y-1">
                  <p className="text-[10px] font-sans font-semibold text-[var(--color-text-muted)] uppercase tracking-wider px-2 py-1">Categorías</p>
                  {CATEGORIES.map(cat => {
                    const { Icon } = cat
                    return (
                      <Link
                        key={cat.slug}
                        to={`/catalog?categoria=${cat.slug}`}
                        onClick={() => setMobileOpen(false)}
                        className="flex items-center gap-3 px-2 py-2.5 rounded-[var(--radius-md)] font-sans text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-background)] hover:text-[var(--color-text-primary)] transition-colors"
                      >
                        <Icon size={18} className="text-[var(--color-action)] shrink-0" strokeWidth={1.5} />
                        {cat.label}
                      </Link>
                    )
                  })}
                </nav>
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </div>

      {/* ── Barra de categorías — desktop ── */}
      <div className="hidden md:block border-t border-[var(--color-border)] bg-[var(--color-surface)]">
        <div className="max-w-[1280px] mx-auto px-6 h-10 flex items-center gap-1 overflow-x-auto">
          <CategoryDropdown />
          <div className="w-px h-5 bg-[var(--color-border)] mx-1" />
          {CATEGORIES.slice(0, 8).map(cat => {
            const { Icon } = cat
            return (
              <Link
                key={cat.slug}
                to={`/catalog?categoria=${cat.slug}`}
                className="shrink-0 flex items-center gap-1.5 px-3 h-8 font-display font-semibold text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-action)] hover:bg-[var(--color-action)]/5 rounded-[var(--radius-md)] transition-colors whitespace-nowrap"
              >
                <Icon size={13} strokeWidth={1.5} />
                {cat.label}
              </Link>
            )
          })}
        </div>
      </div>
    </header>
  )
}
