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

// Mapa de slug → icono para las categorías conocidas
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
    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" className="shrink-0" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="var(--color-action)" />
      <path d="M10 14h12l-1.8 9H11.8L10 14z" stroke="white" strokeWidth="1.5" strokeLinejoin="round" fill="none" />
      <path d="M13 14c0-1.657 1.343-3 3-3s3 1.343 3 3" stroke="white" strokeWidth="1.5" strokeLinecap="round" fill="none" />
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
          <Link to="/profile" onClick={() => setOpen(false)} className="flex items-center gap-2.5 px-3 py-2 font-sans text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-background)] hover:text-[var(--color-text-primary)] transition-colors">
            <UserCircle size={14} /> Mi perfil
          </Link>
          <Link to="/orders" onClick={() => setOpen(false)} className="flex items-center gap-2.5 px-3 py-2 font-sans text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-background)] hover:text-[var(--color-text-primary)] transition-colors">
            <Package size={14} /> Mis pedidos
          </Link>
          {user.roles?.includes('administrador') && (
            <Link to="/admin" onClick={() => setOpen(false)} className="flex items-center gap-2.5 px-3 py-2 font-sans text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-background)] hover:text-[var(--color-text-primary)] transition-colors">
              <Settings size={14} /> Panel admin
            </Link>
          )}
          {user.roles?.includes('vendedor') && (
            <Link to="/vendor" onClick={() => setOpen(false)} className="flex items-center gap-2.5 px-3 py-2 font-sans text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-background)] hover:text-[var(--color-text-primary)] transition-colors">
              <Store size={14} /> Panel vendedor
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
      <button
        onClick={handleOpen}
        className="relative p-2 rounded-[var(--radius-md)] text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] hover:text-[var(--color-text-primary)] transition-colors"
        aria-label={`Notificaciones${unread > 0 ? `, ${unread} sin leer` : ''}`}
      >
        <Bell size={20} />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 h-5 min-w-[20px] px-1 flex items-center justify-center rounded-full bg-[var(--color-error)] text-white font-sans font-bold text-[10px] leading-none">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1.5 w-80 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] shadow-[var(--shadow-lg)] z-50 overflow-hidden">
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
          'flex items-center gap-1.5 px-3 h-9 rounded-[var(--radius-md)] font-display font-semibold text-sm transition-colors whitespace-nowrap',
          open
            ? 'bg-[var(--color-action)] text-white'
            : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-action)]/8 hover:text-[var(--color-action)]'
        )}
      >
        <Menu size={14} />
        Todas las categorías
        <ChevronDown size={11} className={cn('transition-transform duration-200', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="absolute left-0 top-[calc(100%+6px)] w-[340px] bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] shadow-[var(--shadow-lg)] z-[200] overflow-hidden">
          {/* header del panel */}
          <div className="px-4 py-2.5 border-b border-[var(--color-border)] bg-[var(--color-background)]">
            <p className="font-sans text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
              Explorar categorías
            </p>
          </div>

          {/* grid de categorías */}
          <div className="p-2 grid grid-cols-2 gap-1">
            {categories.map(cat => {
              const Icon = ICON_BY_SLUG[cat.slug] || DEFAULT_ICON
              return (
                <button
                  key={cat.slug}
                  onClick={() => { navigate(`/catalog?categoria=${cat.slug}`); setOpen(false) }}
                  className="flex items-center gap-2.5 px-3 py-2.5 rounded-[var(--radius-md)] text-left group hover:bg-[var(--color-action)]/8 transition-colors"
                >
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[var(--radius-sm)] bg-[var(--color-action)]/10 group-hover:bg-[var(--color-action)]/20 transition-colors">
                    <Icon size={14} className="text-[var(--color-action)]" strokeWidth={1.75} />
                  </span>
                  <span className="font-sans text-sm font-medium text-[var(--color-text-secondary)] group-hover:text-[var(--color-text-primary)] transition-colors leading-tight">
                    {cat.nombre}
                  </span>
                </button>
              )
            })}
          </div>

          {/* footer — ver todo */}
          <div className="px-3 pb-2.5">
            <button
              onClick={() => { navigate('/catalog'); setOpen(false) }}
              className="w-full flex items-center justify-center gap-1.5 py-2 rounded-[var(--radius-md)] font-sans text-xs font-semibold text-[var(--color-action)] hover:bg-[var(--color-action)]/8 transition-colors border border-[var(--color-action)]/20 hover:border-[var(--color-action)]/40"
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
  const location = useLocation()

  // Categorías desde la API (MySQL → real)
  const { data: categoriesData } = useQuery({
    queryKey: ['categories'],
    queryFn: () => getCategories().then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })
  const categories = categoriesData || []

  useEffect(() => { setMobileOpen(false) }, [location])

  function toggleDark() {
    document.documentElement.classList.toggle('dark')
    setDark(d => !d)
  }

  return (
    <header className="sticky top-0 z-40 bg-[var(--color-surface)]/95 backdrop-blur-sm border-b border-[var(--color-border)]">
      {/* ── Barra principal ── */}
      <div className="max-w-[1280px] mx-auto px-4 md:px-6 h-16 flex items-center gap-4">
        <Link to="/" className="shrink-0 flex items-center gap-2 group">
          <Logo />
          <span className="font-display font-bold text-lg text-[var(--color-text-primary)] hidden sm:block">
            TiendaYa
          </span>
        </Link>

        <SearchBar className="flex-1 hidden md:flex max-w-xl" />

        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={toggleDark}
            className="p-2 rounded-[var(--radius-md)] text-[var(--color-text-muted)] hover:bg-[var(--color-border)] hover:text-[var(--color-text-primary)] transition-colors"
            aria-label="Cambiar tema"
          >
            {dark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <NotificationBell user={user} />
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
                  {categories.map(cat => {
                    const Icon = ICON_BY_SLUG[cat.slug] || DEFAULT_ICON
                    return (
                      <Link
                        key={cat.slug}
                        to={`/catalog?categoria=${cat.slug}`}
                        onClick={() => setMobileOpen(false)}
                        className="flex items-center gap-3 px-2 py-2.5 rounded-[var(--radius-md)] font-sans text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-background)] hover:text-[var(--color-text-primary)] transition-colors"
                      >
                        <Icon size={18} className="text-[var(--color-action)] shrink-0" strokeWidth={1.5} />
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
      <div className="hidden md:block border-t border-[var(--color-border)] bg-[var(--color-surface)]">
        <div className="max-w-[1280px] mx-auto px-6 h-10 flex items-center gap-1">
          {/* Dropdown fuera del scroll para que no quede recortado */}
          <CategoryDropdown categories={categories} />

          {categories.length > 0 && (
            <div className="w-px h-5 bg-[var(--color-border)] mx-1 shrink-0" />
          )}

          {/* Links individuales en su propio scroll */}
          <div className="flex items-center gap-0.5 overflow-x-auto flex-1 scrollbar-none">
            {categories.map(cat => {
              const Icon = ICON_BY_SLUG[cat.slug] || DEFAULT_ICON
              return (
                <Link
                  key={cat.slug}
                  to={`/catalog?categoria=${cat.slug}`}
                  className="shrink-0 flex items-center gap-1.5 px-3 h-8 font-display font-semibold text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-action)] hover:bg-[var(--color-action)]/8 rounded-[var(--radius-md)] transition-colors whitespace-nowrap"
                >
                  <Icon size={13} strokeWidth={1.5} />
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
