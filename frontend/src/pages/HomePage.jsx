import { useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight } from 'lucide-react'
import { motion, useInView } from 'motion/react'
import { getProducts, getCategories } from '../api/products'
import { ProductCard } from '../components/product/ProductCard'
import { ProductCardSkeleton } from '../components/ui/skeleton'
import { Button } from '../components/ui/button'

const ease = [0.23, 1, 0.32, 1]

function Reveal({ children, className, delay = 0 }) {
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-40px' })
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 22 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.65, ease, delay }}
      className={className}
    >
      {children}
    </motion.div>
  )
}
export default function HomePage() {
  const navigate = useNavigate()
  const { data: featuredData, isLoading } = useQuery({
    queryKey: ['products', 'featured'],
    queryFn: () => getProducts({ page_size: 8 }).then(r => r.data),
  })
  const { data: categoriesData } = useQuery({
    queryKey: ['categories'],
    queryFn: () => getCategories().then(r => r.data),
  })

  const products = featuredData?.items || []
  const categories = categoriesData || []

  function scrollCarousel(dir) {
    carouselRef.current?.scrollBy({ left: dir * 220, behavior: 'smooth' })
  }

  return (
    <div className="bg-[var(--color-surface)] min-h-screen">

      {/* ══════════════════════════════════════════
          HERO — banner completo + texto superpuesto izquierda
      ══════════════════════════════════════════ */}
      <section className="relative overflow-hidden">

        {/* Banner completo — sin recorte */}
        <motion.img
          src="/TiendaYAbanner.png"
          alt=""
          aria-hidden="true"
          className="w-full h-auto block"
          initial={{ opacity: 0, scale: 1.03 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 1, ease }}
        />

        {/* Texto flotando sobre la zona izquierda */}
        <div className="absolute inset-0 flex items-center">
          <div className="w-full pl-10 pr-0">
            <div className="max-w-[460px]">

              <motion.p
                className="font-sans text-[11px] font-semibold uppercase tracking-[0.2em] text-white/70 mb-6"
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, ease, delay: 0.2 }}
              >
                Marketplace guatemalteco
              </motion.p>

              <motion.h1
                className="font-display font-bold text-white leading-[0.95] mb-7"
                style={{ fontSize: 'clamp(2.6rem, 5.5vw, 4.8rem)', letterSpacing: '-0.03em' }}
                initial={{ opacity: 0, y: 24 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.7, ease, delay: 0.28 }}
              >
                Todo lo que<br />
                necesitas,<br />
                en Guatemala.
              </motion.h1>

              <motion.p
                className="font-sans text-white/75 leading-relaxed mb-9"
                style={{ fontSize: '1rem', maxWidth: '300px' }}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, ease, delay: 0.38 }}
              >
                Miles de productos de vendedores verificados.
                Precios en quetzales, envío a todo el país.
              </motion.p>

              <motion.div
                className="flex items-center gap-3 flex-wrap"
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.55, ease, delay: 0.46 }}
              >
                <Button
                  size="lg"
                  onClick={() => navigate('/catalog')}
                  className="btn-pulse bg-white text-[var(--color-action)] hover:bg-white/95 font-bold shadow-[0_4px_20px_rgba(0,0,0,0.22)]"
                >
                  Explorar productos <ArrowRight size={15} />
                </Button>
                <Button
                  size="lg"
                  onClick={() => navigate('/register')}
                  className="bg-white/15 text-white border border-white/30 hover:bg-white/25 backdrop-blur-sm"
                >
                  Empezar a vender
                </Button>
              </motion.div>

            </div>
          </div>
        </div>

      </section>


      {/* ══════════════════════════════════════════
          PRODUCTOS DESTACADOS
      ══════════════════════════════════════════ */}
      <section className="py-20 lg:py-28 bg-[var(--color-background)]">
        <div className="max-w-[1320px] mx-auto px-6 lg:px-12">

          <Reveal className="flex items-end justify-between mb-12">
            <div>
              <p className="font-sans text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-text-muted)] mb-3">
                Selección
              </p>
              <h2
                className="font-display font-bold text-[var(--color-text-primary)] leading-[0.95]"
                style={{ fontSize: 'clamp(1.8rem, 4vw, 2.8rem)', letterSpacing: '-0.025em' }}
              >
                Más vendidos
              </h2>
            </div>
            <Button variant="secondary" size="sm" asChild>
              <Link to="/catalog" className="flex items-center gap-1.5">
                Ver todo <ArrowRight size={13} />
              </Link>
            </Button>
          </Reveal>

          {isLoading ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 lg:gap-5">
              {Array.from({ length: 8 }).map((_, i) => <ProductCardSkeleton key={i} />)}
            </div>
          ) : products.length > 0 ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 lg:gap-5">
              {products.map((product, i) => (
                <motion.div
                  key={product._id}
                  initial={{ opacity: 0, y: 18 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: '-20px' }}
                  transition={{ delay: (i % 4) * 0.07, duration: 0.55, ease }}
                >
                  <ProductCard product={product} />
                </motion.div>
              ))}
            </div>
          ) : (
            <p className="text-center py-24 font-sans text-[var(--color-text-muted)]">
              No hay productos disponibles en este momento.
            </p>
          )}

        </div>
      </section>

      {/* ══════════════════════════════════════════
          TRUST — franja de texto limpia
      ══════════════════════════════════════════ */}
      <Reveal>
        <section className="border-y border-[var(--color-border)] bg-[var(--color-surface)] py-5">
          <div className="max-w-[1320px] mx-auto px-6 lg:px-12">
            <p className="font-sans text-[13px] text-[var(--color-text-muted)] text-center leading-relaxed tracking-wide">
              Pagos protegidos con SSL
              <span className="inline-block mx-4 opacity-30">·</span>
              Envío a todo Guatemala en 24–72 h
              <span className="inline-block mx-4 opacity-30">·</span>
              Vendedores verificados
              <span className="inline-block mx-4 opacity-30">·</span>
              Soporte en español
            </p>
          </div>
        </section>
      </Reveal>

      {/* ══════════════════════════════════════════
          CTA VENDEDORES — celeste split layout
      ══════════════════════════════════════════ */}
      <Reveal>
        <section
          className="py-20 lg:py-28 overflow-hidden relative"
          style={{ backgroundColor: '#29B6F6' }}
        >
          {/* Sutil textura de luz */}
          <div
            className="absolute inset-0 pointer-events-none opacity-[0.12]"
            style={{
              backgroundImage: 'radial-gradient(ellipse at 30% 50%, white 0%, transparent 55%)',
            }}
          />
          <div className="relative max-w-6xl mx-auto px-6 lg:px-12 flex flex-col lg:flex-row items-center gap-10 lg:gap-16">

            {/* Logo grande — izquierda */}
            <motion.div
              className="shrink-0 flex items-center justify-center lg:justify-start"
              initial={{ opacity: 0, x: -32 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ duration: 0.7, ease }}
            >
              <img
                src="/TiendaYAlogo.png"
                alt="TiendaYa"
                className="w-52 lg:w-72 xl:w-80 h-auto object-contain drop-shadow-2xl"
              />
            </motion.div>

            {/* Texto — derecha */}
            <motion.div
              className="flex-1 text-center lg:text-left"
              initial={{ opacity: 0, x: 32 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ duration: 0.7, ease, delay: 0.1 }}
            >
              <p className="font-sans text-[11px] font-semibold uppercase tracking-[0.2em] text-white/60 mb-4">
                Para vendedores
              </p>
              <h2
                className="font-display font-bold text-white leading-[0.95] mb-5"
                style={{ fontSize: 'clamp(2rem, 4.5vw, 3.2rem)', letterSpacing: '-0.03em' }}
              >
                Vende en TiendaYa.<br />
                <span className="text-white/70">Sin complicaciones.</span>
              </h2>
              <p className="font-sans text-white/65 leading-relaxed mb-8" style={{ fontSize: '1rem', maxWidth: '480px' }}>
                Publica tus productos y llega a miles de compradores
                en toda Guatemala. Sin comisiones ocultas.
              </p>
              <Button
                size="lg"
                onClick={() => navigate('/register')}
                className="bg-white hover:bg-white/95 active:scale-[.97] font-bold shadow-[0_8px_40px_rgba(0,0,0,0.18)]"
                style={{ color: '#29B6F6' }}
              >
                Comenzar gratis <ArrowRight size={16} />
              </Button>
            </motion.div>

          </div>
        </section>
      </Reveal>

    </div>
  )
}
