import { useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, ShieldCheck, Truck, CreditCard, Headphones, ChevronLeft } from 'lucide-react'
import { getProducts, getCategories } from '../api/products'
import { ProductCard } from '../components/product/ProductCard'
import { ProductCardSkeleton } from '../components/ui/skeleton'
import { Button } from '../components/ui/button'

const CATEGORY_ICONS = {
  computadoras: '💻',
  celulares: '📱',
  audio: '🎧',
  camisas: '👕',
  pantalones: '👖',
  calzado: '👟',
  libros: '📚',
  alimentos: '🥗',
  hogar: '🏠',
  deportes: '⚽',
  herramientas: '🔧',
  juguetes: '🧸',
}

const TRUST_SIGNALS = [
  { icon: ShieldCheck, title: 'Compra segura', desc: 'Pagos protegidos con cifrado SSL' },
  { icon: Truck, title: 'Envío a todo Guatemala', desc: 'Cobertura nacional en 24–72 h' },
  { icon: CreditCard, title: 'Múltiples métodos de pago', desc: 'Tarjeta, transferencia o contra entrega' },
  { icon: Headphones, title: 'Soporte en español', desc: 'Atención 24/7 para resolver tus dudas' },
]

export default function HomePage() {
  const navigate = useNavigate()
  const carouselRef = useRef(null)

  const { data: featuredData, isLoading: loadingFeatured } = useQuery({
    queryKey: ['products', 'featured'],
    queryFn: () => getProducts({ page_size: 8 }).then((r) => r.data),
  })

  const { data: categoriesData } = useQuery({
    queryKey: ['categories'],
    queryFn: () => getCategories().then((r) => r.data),
  })

  const products = featuredData?.items || []
  const categories = categoriesData || []

  function scrollCarousel(dir) {
    if (!carouselRef.current) return
    carouselRef.current.scrollBy({ left: dir * 220, behavior: 'smooth' })
  }

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <section className="relative overflow-hidden">
        <div
          className="min-h-[520px] lg:min-h-[600px] flex flex-col lg:flex-row"
          style={{
            background:
              'linear-gradient(135deg, var(--color-action) 0%, var(--color-jade) 100%)',
          }}
        >
          <div className="flex-1 flex flex-col justify-center px-8 py-16 lg:px-16 lg:py-20 text-white z-10">
            <span
              className="inline-flex items-center gap-2 text-xs font-sans font-semibold uppercase tracking-widest mb-4 opacity-80"
            >
              Marketplace guatemalteco
            </span>
            <h1
              className="font-display font-bold text-4xl lg:text-6xl leading-tight mb-6"
              style={{ textShadow: '0 2px 24px rgba(0,0,0,0.15)' }}
            >
              Compra y vende<br />en un solo lugar
            </h1>
            <p className="font-sans text-lg opacity-90 mb-8 max-w-md leading-relaxed">
              Miles de productos de vendedores verificados en todo Guatemala. Precios en quetzales, envío nacional.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button
                size="lg"
                onClick={() => navigate('/catalog')}
                className="bg-white text-[var(--color-action)] hover:bg-white/90 shadow-[var(--shadow-lg)]"
              >
                Explorar productos
                <ChevronRight size={18} />
              </Button>
              <Button
                size="lg"
                variant="ghost"
                onClick={() => navigate('/register')}
                className="text-white border border-white/40 hover:bg-white/10"
              >
                Crear cuenta gratis
              </Button>
            </div>
          </div>

          <div className="flex-1 relative hidden lg:flex items-center justify-center">
            <div
              className="absolute inset-0 opacity-10"
              style={{
                backgroundImage:
                  'radial-gradient(circle at 60% 50%, white 0%, transparent 70%)',
              }}
            />
            <div className="relative grid grid-cols-2 gap-4 p-8 max-w-sm">
              {['💻', '📱', '👟', '📚'].map((emoji, i) => (
                <div
                  key={i}
                  className="aspect-square rounded-[var(--radius-xl)] bg-white/20 backdrop-blur-sm flex items-center justify-center text-5xl shadow-[var(--shadow-lg)]"
                  style={{ transform: i % 2 === 1 ? 'translateY(16px)' : 'none' }}
                >
                  {emoji}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {categories.length > 0 && (
        <section className="py-10 bg-[var(--color-surface)] border-b border-[var(--color-border)]">
          <div className="max-w-7xl mx-auto px-4">
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-display font-bold text-xl text-[var(--color-text-primary)]">
                Categorías
              </h2>
              <div className="flex gap-2">
                <button
                  onClick={() => scrollCarousel(-1)}
                  className="h-8 w-8 flex items-center justify-center rounded-full border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] transition-colors"
                >
                  <ChevronLeft size={16} />
                </button>
                <button
                  onClick={() => scrollCarousel(1)}
                  className="h-8 w-8 flex items-center justify-center rounded-full border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] transition-colors"
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>

            <div
              ref={carouselRef}
              className="flex gap-3 overflow-x-auto pb-2 scrollbar-hide"
              style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
            >
              {categories.map((cat) => (
                <Link
                  key={cat.slug || cat._id}
                  to={`/catalog?categoria=${cat.slug}`}
                  className="flex-shrink-0 flex flex-col items-center gap-2 px-5 py-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-background)] hover:border-[var(--color-action)] hover:shadow-[var(--shadow-md)] transition-all duration-200 min-w-[120px]"
                >
                  <span className="text-3xl">{CATEGORY_ICONS[cat.slug] || '📦'}</span>
                  <span className="font-sans text-xs font-semibold text-[var(--color-text-primary)] text-center whitespace-nowrap">
                    {cat.nombre}
                  </span>
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      <section className="py-14 max-w-7xl mx-auto px-4">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h2 className="font-display font-bold text-2xl text-[var(--color-text-primary)]">
              Productos destacados
            </h2>
            <p className="font-sans text-sm text-[var(--color-text-secondary)] mt-1">
              Los más populares de nuestra tienda
            </p>
          </div>
          <Button variant="secondary" size="sm" asChild>
            <Link to="/catalog">
              Ver todos <ChevronRight size={14} />
            </Link>
          </Button>
        </div>

        {loadingFeatured ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <ProductCardSkeleton key={i} />
            ))}
          </div>
        ) : products.length > 0 ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {products.map((product) => (
              <ProductCard key={product._id} product={product} />
            ))}
          </div>
        ) : (
          <div className="text-center py-20 text-[var(--color-text-muted)]">
            <span className="text-5xl mb-4 block">📦</span>
            <p className="font-sans text-base">No hay productos disponibles en este momento.</p>
          </div>
        )}
      </section>

      <section className="py-14 bg-[var(--color-surface)] border-t border-[var(--color-border)]">
        <div className="max-w-7xl mx-auto px-4">
          <h2 className="font-display font-bold text-2xl text-[var(--color-text-primary)] text-center mb-10">
            Por qué elegir TiendaYa
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {TRUST_SIGNALS.map((signal) => {
              const Icon = signal.icon
              return (
                <div
                  key={signal.title}
                  className="flex flex-col items-center text-center gap-3 p-6 rounded-[var(--radius-lg)] bg-[var(--color-background)] border border-[var(--color-border)]"
                >
                  <div className="h-12 w-12 rounded-full flex items-center justify-center bg-[var(--color-action)]/10">
                    <Icon size={22} className="text-[var(--color-action)]" />
                  </div>
                  <h3 className="font-display font-semibold text-base text-[var(--color-text-primary)]">
                    {signal.title}
                  </h3>
                  <p className="font-sans text-sm text-[var(--color-text-secondary)] leading-relaxed">
                    {signal.desc}
                  </p>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      <section
        className="py-16 text-white text-center"
        style={{ background: 'linear-gradient(135deg, var(--color-jade) 0%, var(--color-action) 100%)' }}
      >
        <div className="max-w-2xl mx-auto px-4">
          <h2 className="font-display font-bold text-3xl mb-4">
            ¿Eres vendedor?
          </h2>
          <p className="font-sans text-base opacity-90 mb-8">
            Publica tus productos y llega a miles de compradores en toda Guatemala sin comisiones ocultas.
          </p>
          <Button
            size="lg"
            className="bg-white text-[var(--color-action)] hover:bg-white/90"
            onClick={() => navigate('/register')}
          >
            Empezar a vender gratis
          </Button>
        </div>
      </section>
    </div>
  )
}
