import { useState, useEffect, useRef } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Search, ShoppingCart, ChevronDown, Menu, X,
  LogOut, Package, Settings, Sun, Moon, UserCircle,
  Monitor, Smartphone, Headphones, Shirt, Layers, ShoppingBag,
  BookOpen, Apple, Home, Dumbbell, Wrench, Gamepad2,
  Bell, Store,
} from 'lucide-react'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import { Sheet, SheetTrigger, SheetContent } from '../ui/sheet'
import { useAuth } from '../../context/AuthContext'
import { useCart } from '../../context/CartContext'
import { getCategories } from '../../api/products'
import { getUnreadCount, getNotifications, markAllAsRead } from '../../api/notifications'
import { cn } from '../../lib/utils'

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

function Logo() {
  return (
    <img
      src="/TiendaYAlogo.png"
      alt="TiendaYa"
      className="h-11 w-auto shrink-0 object-contain logo-hover"
    />
  )
}

function SearchBar({ className, onSearch }) {
  const [q, setQ] = useState('')
  const [focused, setFocused] = useState(false)
  const navigate = useNavigate()
  function submit(e) {
    e.preventDefault()
    if (q.trim()) { navigate(`/catalog?q=${encodeURIComponent(q.trim())}`); onSearch?.() }
  }
  return (
    <form onSubmit={submit} className={cn('relative flex items-center', className)}>
      <Search
        size={15}
        className={cn(
          'absolute left-3.5 pointer-events-none transition-colors duration-150',
          focused ? 'text-[#29B6F6]' : 'text-[var(--color-text-muted)]'
        )}
      />
      <input
        value={q}
        onChange={e => setQ(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        placeholder="Buscar productos..."
        className="w-full h-10 pl-9 pr-4 bg-[var(--color-background)] border border-[var(--color-border)] rounded-full font-sans text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[#29B6F6] focus:ring-2 focus:ring-[#29B6F6]/20 transition-all duration-200"
      />
    </form>
  )
}

function IconBtn({ onClick, label, children, className }) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      className={cn(
        'relative h-9 w-9 flex items-center justify-center rounded-full text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] hover:text-[var(--color-text-primary)] transition-all duration-150',
        className
      )}
    >
      {children}
    </button>
  )
}

function CartIcon() {
  const { cart } = useCart()
  const count = cart?.items?.length || 0
  return (
    <Link
      to="/cart"
      className="relative h-9 w-9 flex items-center justify-center rounded-full text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] hover:text-[var(--color-text-primary)] transition-all duration-150"
      aria-label={`Carrito, ${count} artículos`}
    >
      <ShoppingCart size={19} />
      {count > 0 && (
        <span className="absolute -top-0.5 -right-0.5 h-[18px] min-w-[18px] px-1 flex items-center justify-center rounded-full bg-[#29B6F6] text-white font-sans font-bold text-[9px] leading-none shadow-sm">
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
        <Button variant="ghost" size="sm" asChild>
          <Link to="/login">Entrar</Link>
        </Button>
        <Button size="sm" asChild style={{ backgroundColor: '#29B6F6', color: 'white' }}
          className="hover:opacity-90 active:scale-95">
          <Link to="/register">Registrarse</Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className={cn(
          'flex items-center gap-2 pl-1 pr-2.5 py-1 rounded-full transition-all duration-150',
          open
            ? 'bg-[var(--color-border)]'
            : 'hover:bg-[var(--color-border)]'
        )}
      >
        <div
          className="h-8 w-8 rounded-full flex items-center justify-center text-white font-display font-bold text-sm shadow-sm"
          style={{ background: 'linear-gradient(135deg, #29B6F6, #0288D1)' }}
        >
          {user.nombre?.[0]?.toUpperCase() || 'U'}
        </div>
        <span className="font-sans text-sm font-medium text-[var(--color-text-primary)] hidden lg:block max-w-[80px] truncate">
          {user.nombre}
        </span>
        <ChevronDown size={12} className={cn('text-[var(--color-text-muted)] transition-transform duration-200', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-56 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-xl)] shadow-[0_16px_48px_rgba(0,0,0,0.12)] py-1.5 z-50 animate-scale-in">
          <div className="px-3.5 py-2.5 mb-1">
            <p className="font-display font-semibold text-sm text-[var(--color-text-primary)] truncate">{user.nombre} {user.apellido}</p>
            <p className="font-sans text-xs text-[var(--color-text-muted)] truncate">{user.email}</p>
          </div>
          <div className="border-t border-[var(--color-border)] pt-1">
            <Link to="/profile" onClick={() => setOpen(false)} className="flex items-center gap-2.5 px-3.5 py-2 font-sans text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-background)] hover:text-[var(--color-text-primary)] transition-colors rounded-md mx-1">
              <UserCircle size={14} /> Mi perfil
            </Link>
            <Link to="/orders" onClick={() => setOpen(false)} className="flex items-center gap-2.5 px-3.5 py-2 font-sans text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-background)] hover:text-[var(--color-text-primary)] transition-colors rounded-md mx-1">
              <Package size={14} /> Mis pedidos
            </Link>
            {user.roles?.includes('administrador') && (
              <Link to="/admin" onClick={() => setOpen(false)} className="flex items-center gap-2.5 px-3.5 py-2 font-sans text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-background)] hover:text-[var(--color-text-primary)] transition-colors rounded-md mx-1">
                <Settings size={14} /> Panel admin
              </Link>
            )}
            {user.roles?.includes('vendedor') && (
              <Link to="/vendor" onClick={() => setOpen(false)} className="flex items-center gap-2.5 px-3.5 py-2 font-sans text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-background)] hover:text-[var(--color-text-primary)] transition-colors rounded-md mx-1">
                <Store size={14} /> Panel vendedor
              </Link>
            )}
          </div>
          <div className="border-t border-[var(--color-border)] mt-1 pt-1">
            <button onClick={() => { signOut(); setOpen(false) }} className="flex w-full items-center gap-2.5 px-3.5 py-2 font-sans text-sm text-[var(--color-error)] hover:bg-[var(--color-error)]/8 transition-colors rounded-md mx-1 w-[calc(100%-8px)]">
              <LogOut size={14} /> Cerrar sesión
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function NotificationBell({ user }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const queryClient = useQueryClient()

  const { data: countData } = useQuery({
    queryKey: ['notif-count'],
    queryFn: () => getUnreadCount().then(r => r.data),
    refetchInterval: 60000,
    enabled: !!user,
    staleTime: 30000,
  })
  const unread = countData?.count || 0

  const { data: notifs } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => getNotifications().then(r => r.data),
    enabled: open && !!user,
    staleTime: 30000,
  })

  useEffect(() => {
    function handler(e) { if (!ref.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  async function handleOpen() {
    setOpen(v => !v)
    if (!open && unread > 0) {
      await markAllAsRead()
      queryClient.invalidateQueries({ queryKey: ['notif-count'] })
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
    }
  }

  if (!user) return null

  return (
    <div className="relative" ref={ref}>
      <IconBtn onClick={handleOpen} label={`Notificaciones${unread > 0 ? `, ${unread} sin leer` : ''}`}>
        <Bell size={19} />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 h-[18px] min-w-[18px] px-1 flex items-center justify-center rounded-full bg-[var(--color-error)] text-white font-sans font-bold text-[9px] leading-none shadow-sm">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </IconBtn>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-xl)] shadow-[0_16px_48px_rgba(0,0,0,0.12)] z-50 overflow-hidden animate-scale-in">
          <div className="px-4 py-3 border-b border-[var(--color-border)]">
            <p className="font-display font-semibold text-sm text-[var(--color-text-primary)]">Notificaciones</p>
          </div>
          <div className="max-h-80 overflow-y-auto">
            {!notifs ? (
              <p className="px-4 py-4 font-sans text-sm text-[var(--color-text-muted)] text-center">Cargando...</p>
            ) : notifs.length === 0 ? (
              <p className="px-4 py-6 font-sans text-sm text-[var(--color-text-muted)] text-center">Sin notificaciones</p>
            ) : (
              notifs.slice(0, 15).map(n => (
                <div key={n.id} className="px-4 py-3 border-b border-[var(--color-border)] last:border-0 hover:bg-[var(--color-background)]">
                  <p className="font-display font-semibold text-xs text-[var(--color-text-primary)]">{n.titulo}</p>
                  <p className="font-sans text-xs text-[var(--color-text-secondary)] mt-0.5 line-clamp-2">{n.mensaje}</p>
                  <p className="font-sans text-[10px] text-[var(--color-text-muted)] mt-1">{n.fecha?.slice(0, 10)}</p>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function CategoryDropdown({ categories }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const navigate = useNavigate()

  useEffect(() => {
    function handler(e) { if (!ref.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  useEffect(() => {
    function handler(e) { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  return (
    <div className="relative shrink-0" ref={ref}>
      <button
        onClick={() => setOpen(v => !v)}
        className={cn(
          'flex items-center gap-1.5 px-3.5 h-8 rounded-full font-display font-semibold text-[13px] transition-all duration-150 whitespace-nowrap',
          open
            ? 'text-white shadow-sm'
            : 'text-[var(--color-text-secondary)] hover:text-white'
        )}
        style={open
          ? { backgroundColor: '#29B6F6' }
          : undefined
        }
        onMouseEnter={e => { if (!open) e.currentTarget.style.backgroundColor = '#29B6F6' }}
        onMouseLeave={e => { if (!open) e.currentTarget.style.backgroundColor = '' }}
      >
        <Menu size={13} />
        Categorías
        <ChevronDown size={11} className={cn('transition-transform duration-200', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="absolute left-0 top-[calc(100%+8px)] w-[340px] bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-xl)] shadow-[var(--shadow-xl)] z-[200] overflow-hidden animate-scale-in">
          <div className="px-4 py-2.5 border-b border-[var(--color-border)]" style={{ background: 'linear-gradient(to right, #29B6F6/8, transparent)' }}>
            <p className="font-sans text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
              Explorar categorías
            </p>
          </div>
          <div className="p-2 grid grid-cols-2 gap-0.5">
            {categories.map(cat => {
              const Icon = ICON_BY_SLUG[cat.slug] || DEFAULT_ICON
              return (
                <button
                  key={cat.slug}
                  onClick={() => { navigate(`/catalog?categoria=${cat.slug}`); setOpen(false) }}
                  className="flex items-center gap-2 px-3 py-2.5 rounded-[var(--radius-md)] text-left hover:bg-[#29B6F6]/8 transition-colors group"
                >
                  <Icon size={13} className="text-[#29B6F6] shrink-0" strokeWidth={1.5} />
                  <span className="font-sans text-sm font-medium text-[var(--color-text-secondary)] group-hover:text-[var(--color-text-primary)] transition-colors leading-tight">
                    {cat.nombre}
                  </span>
                </button>
              )
            })}
          </div>
          <div className="px-3 pb-2.5">
            <button
              onClick={() => { navigate('/catalog'); setOpen(false) }}
              className="w-full flex items-center justify-center gap-1.5 py-2 rounded-full font-sans text-xs font-semibold transition-all duration-150 text-white"
              style={{ backgroundColor: '#29B6F6' }}
              onMouseEnter={e => e.currentTarget.style.opacity = '0.88'}
              onMouseLeave={e => e.currentTarget.style.opacity = '1'}
            >
              Ver todo el catálogo
              <ChevronDown size={11} className="-rotate-90" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export function Header() {
  const { user, signOut } = useAuth()
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'))
  const [mobileOpen, setMobileOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const location = useLocation()

  const { data: categoriesData } = useQuery({
    queryKey: ['categories'],
    queryFn: () => getCategories().then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })
  const categories = categoriesData || []

  // Categoría activa desde la URL
  const params = new URLSearchParams(location.search)
  const activeSlug = location.pathname === '/catalog' ? params.get('categoria') : null

  useEffect(() => { setMobileOpen(false) }, [location])

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 8)
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  function toggleDark() {
    document.documentElement.classList.toggle('dark')
    setDark(d => !d)
  }

  return (
    <header
      className={cn(
        'sticky top-0 z-40 transition-all duration-300',
        scrolled
          ? 'bg-[var(--color-surface)]/95 backdrop-blur-md shadow-[0_2px_20px_rgba(0,0,0,0.08)] border-b border-[var(--color-border)]'
          : 'bg-[var(--color-surface)] border-b border-transparent'
      )}
    >
      {/* Línea de acento celeste en la parte superior */}
      <div className="h-[3px] w-full" style={{ background: 'linear-gradient(to right, #29B6F6, #0288D1, #29B6F6)' }} />

      {/* ── Barra principal ── */}
      <div className="max-w-[1320px] mx-auto px-4 md:px-6 lg:px-12 h-[68px] flex items-center gap-4">
        <Link to="/" className="shrink-0 flex items-center hover:opacity-80 active:scale-[.97] transition-all duration-150">
          <Logo />
        </Link>

        <SearchBar className="flex-1 hidden md:flex max-w-xl" />

        <div className="ml-auto flex items-center gap-0.5">
          <IconBtn onClick={toggleDark} label="Cambiar tema">
            {dark ? <Sun size={18} /> : <Moon size={18} />}
          </IconBtn>
          <NotificationBell user={user} />
          <CartIcon />

          {/* Separador visual */}
          <span className="h-5 w-px bg-[var(--color-border)] mx-1.5 hidden sm:block" />

          <UserMenu user={user} signOut={signOut} />

          {/* Menú móvil */}
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger asChild>
              <button className="md:hidden h-9 w-9 flex items-center justify-center rounded-full text-[var(--color-text-muted)] hover:bg-[var(--color-border)]">
                <Menu size={20} />
              </button>
            </SheetTrigger>
            <SheetContent side="right" title="Menú">
              <div className="px-5 py-4 space-y-4">
                <SearchBar onSearch={() => setMobileOpen(false)} />
                <nav className="space-y-1">
                  <p className="text-[10px] font-sans font-semibold text-[var(--color-text-muted)] uppercase tracking-wider px-2 py-1">Categorías</p>
                  {categories.map(cat => {
                    const Icon = ICON_BY_SLUG[cat.slug] || DEFAULT_ICON
                    return (
                      <Link
                        key={cat.slug}
                        to={`/catalog?categoria=${cat.slug}`}
                        onClick={() => setMobileOpen(false)}
                        className="flex items-center gap-3 px-2 py-2.5 rounded-[var(--radius-md)] font-sans text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-background)] hover:text-[var(--color-text-primary)] transition-colors"
                      >
                        <Icon size={18} className="shrink-0" style={{ color: '#29B6F6' }} strokeWidth={1.5} />
                        {cat.nombre}
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
      <div className="hidden md:block border-t border-[var(--color-border)]">
        <div className="max-w-[1320px] mx-auto px-6 lg:px-12 h-10 flex items-center gap-2">
          <CategoryDropdown categories={categories} />

          {categories.length > 0 && (
            <span className="h-4 w-px bg-[var(--color-border)] shrink-0" />
          )}

          <div className="flex items-center gap-0.5 overflow-x-auto flex-1 scrollbar-none">
            {categories.map(cat => {
              const Icon = ICON_BY_SLUG[cat.slug] || DEFAULT_ICON
              const isActive = activeSlug === cat.slug
              return (
                <Link
                  key={cat.slug}
                  to={`/catalog?categoria=${cat.slug}`}
                  className={cn(
                    'shrink-0 flex items-center gap-1.5 px-3 h-7 rounded-full font-sans text-[12px] font-medium transition-all duration-150 whitespace-nowrap',
                    isActive
                      ? 'text-white'
                      : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-border)]'
                  )}
                  style={isActive ? { backgroundColor: '#29B6F6' } : undefined}
                >
                  <Icon size={12} strokeWidth={1.5} />
                  {cat.nombre}
                </Link>
              )
            })}
          </div>
        </div>
      </div>
    </header>
  )
}
