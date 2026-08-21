import { cn } from '../../lib/utils'

/* ── Renders por familia de categoría ─────────────────────────────── */

function MetricCell({ label, value, mono = false }) {
  if (!value && value !== 0) return null
  return (
    <div className="flex flex-col items-center gap-0.5 min-w-0">
      <span className={cn('text-[var(--color-text-primary)] font-semibold leading-none truncate w-full text-center',
        mono ? 'font-mono text-2xl' : 'font-display text-xl'
      )}>
        {value}
      </span>
      <span className="text-[10px] font-sans font-medium text-[var(--color-text-muted)] uppercase tracking-wider text-center">
        {label}
      </span>
    </div>
  )
}

function ElectronicaPanel({ atributos }) {
  const fields = [
    { label: 'Procesador', key: 'procesador', short: (v) => v?.split(' ').slice(0, 3).join(' ') },
    { label: 'RAM', key: 'ram_gb', short: (v) => `${v} GB` },
    { label: 'Almacen.', key: 'almacenamiento_gb', short: (v) => v >= 1000 ? `${v/1000} TB` : `${v} GB` },
    { label: 'Pantalla', key: 'pulgadas', short: (v) => `${v}"` },
    { label: 'Almacen.', key: 'almacenamiento', short: (v) => v },
    { label: 'Batería', key: 'bateria_mah', short: (v) => `${v} mAh` },
    { label: 'Cámara', key: 'camara_mp', short: (v) => `${v} MP` },
  ]
  const visible = fields.filter(f => atributos?.[f.key] !== undefined).slice(0, 4)
  if (!visible.length) return null
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-background)] p-4">
      <div className={cn('grid gap-4', visible.length <= 2 ? 'grid-cols-2' : visible.length === 3 ? 'grid-cols-3' : 'grid-cols-4')}>
        {visible.map(f => (
          <MetricCell
            key={f.key}
            label={f.label}
            value={f.short(atributos[f.key])}
            mono={f.key === 'ram_gb' || f.key === 'almacenamiento_gb' || f.key === 'bateria_mah'}
          />
        ))}
      </div>
    </div>
  )
}

function RopaPanel({ atributos }) {
  const tallas = ['XS', 'S', 'M', 'L', 'XL', 'XXL']
  const tallaActual = atributos?.talla
  const colores = {
    negro: '#1a1a1a', blanco: '#ffffff', azul: '#2563EB', rojo: '#DC2626',
    verde: '#16A34A', amarillo: '#EAB308', gris: '#6B7280', beige: '#D4B896',
    'azul marino': '#1e3a5f', rosa: '#EC4899', morado: '#7C3AED', naranja: '#EA580C',
    café: '#92400E', celeste: '#0EA5E9',
  }
  const colorActual = atributos?.color?.toLowerCase()
  const colorHex = colores[colorActual]

  return (
    <div className="space-y-3">
      {atributos?.talla && (
        <div>
          <p className="text-xs font-sans font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Talla</p>
          <div className="flex flex-wrap gap-2">
            {tallas.map(t => (
              <span
                key={t}
                className={cn(
                  'h-9 min-w-[36px] px-2 flex items-center justify-center rounded-[var(--radius-md)]',
                  'font-sans text-sm font-medium border transition-colors',
                  t === tallaActual
                    ? 'bg-[var(--color-action)] text-white border-[var(--color-action)]'
                    : 'bg-[var(--color-surface)] text-[var(--color-text-secondary)] border-[var(--color-border)] opacity-40'
                )}
              >
                {t}
              </span>
            ))}
          </div>
        </div>
      )}
      {atributos?.color && (
        <div>
          <p className="text-xs font-sans font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">
            Color: <span className="normal-case text-[var(--color-text-primary)] font-semibold">{atributos.color}</span>
          </p>
          {colorHex && (
            <div
              className="h-8 w-8 rounded-full border-2 border-[var(--color-border)] shadow-sm"
              style={{ backgroundColor: colorHex }}
            />
          )}
        </div>
      )}
      {atributos?.material && (
        <p className="text-sm font-sans text-[var(--color-text-secondary)]">
          <span className="font-medium text-[var(--color-text-primary)]">Material:</span>{' '}
          {atributos.material}
        </p>
      )}
    </div>
  )
}

function LibrosPanel({ atributos }) {
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] divide-y divide-[var(--color-border)]">
      {atributos?.autor && (
        <div className="px-4 py-3">
          <p className="text-[10px] font-sans font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">Autor</p>
          <p className="font-display font-semibold text-[var(--color-text-primary)] mt-0.5">{atributos.autor}</p>
        </div>
      )}
      <div className="px-4 py-3 grid grid-cols-2 gap-4">
        {atributos?.paginas && (
          <div>
            <p className="text-[10px] font-sans font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">Páginas</p>
            <p className="font-mono font-bold text-xl text-[var(--color-text-primary)] mt-0.5">{atributos.paginas}</p>
          </div>
        )}
        {atributos?.editorial && (
          <div>
            <p className="text-[10px] font-sans font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">Editorial</p>
            <p className="font-sans text-sm text-[var(--color-text-primary)] mt-0.5">{atributos.editorial}</p>
          </div>
        )}
      </div>
      {atributos?.isbn && (
        <div className="px-4 py-3">
          <p className="text-[10px] font-sans font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">ISBN</p>
          <p className="font-mono text-sm text-[var(--color-text-secondary)] mt-0.5">{atributos.isbn}</p>
        </div>
      )}
    </div>
  )
}

function AlimentosPanel({ atributos }) {
  const icons = [
    { key: 'apto_vegano',  label: 'Vegano',      icon: '🌿', color: 'text-green-600 bg-green-50' },
    { key: 'sin_gluten',   label: 'Sin gluten',   icon: '🌾', color: 'text-amber-600 bg-amber-50' },
    { key: 'organico',     label: 'Orgánico',     icon: '♻️', color: 'text-teal-600 bg-teal-50'  },
  ]
  const activeFlags = icons.filter(i => atributos?.[i.key])
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {atributos?.peso_g && (
          <div className="flex items-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-border)] px-3 py-2">
            <span className="text-lg">⚖️</span>
            <div>
              <p className="font-mono font-bold text-lg text-[var(--color-text-primary)] leading-none">
                {atributos.peso_g >= 1000 ? `${atributos.peso_g/1000}kg` : `${atributos.peso_g}g`}
              </p>
              <p className="text-[10px] font-sans text-[var(--color-text-muted)] uppercase">Peso</p>
            </div>
          </div>
        )}
        {activeFlags.map(flag => (
          <div key={flag.key} className={cn('flex items-center gap-1.5 rounded-[var(--radius-md)] px-3 py-2', flag.color)}>
            <span className="text-base">{flag.icon}</span>
            <span className="text-xs font-sans font-semibold">{flag.label}</span>
          </div>
        ))}
      </div>
      {atributos?.origen && (
        <p className="text-sm font-sans text-[var(--color-text-secondary)]">
          <span className="font-medium text-[var(--color-text-primary)]">Origen:</span> {atributos.origen}
        </p>
      )}
    </div>
  )
}

function GenericPanel({ atributos }) {
  const fields = [
    { label: 'Peso', key: 'peso_kg', fmt: v => `${v} kg` },
    { label: 'Material', key: 'material', fmt: v => v },
    { label: 'Dimensiones', key: 'dimensiones', fmt: v => v },
    { label: 'Color', key: 'color', fmt: v => v },
    { label: 'Marca', key: 'marca', fmt: v => v },
    { label: 'Edad', key: 'edad_recomendada', fmt: v => v },
    { label: 'Deporte', key: 'deporte', fmt: v => v },
    { label: 'Tipo', key: 'tipo', fmt: v => v },
  ]
  const visible = fields.filter(f => atributos?.[f.key]).slice(0, 4)
  if (!visible.length) return null
  const cols = visible.length <= 2 ? 'grid-cols-2' : visible.length === 3 ? 'grid-cols-3' : 'grid-cols-4'
  return (
    <div className={cn('grid gap-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-background)] p-4', cols)}>
      {visible.map(f => (
        <MetricCell key={f.key} label={f.label} value={f.fmt(atributos[f.key])} />
      ))}
    </div>
  )
}

/* ── Router principal ─────────────────────────────────────────────── */

const ELECTRONICS = ['computadoras', 'celulares', 'audio']
const ROPA        = ['camisas', 'pantalones', 'calzado']

export function CategoryAttrPanel({ categoria, atributos }) {
  const slug = typeof categoria === 'object' ? categoria?.slug : categoria
  if (!atributos || !slug) return null

  if (ELECTRONICS.includes(slug)) return <ElectronicaPanel atributos={atributos} />
  if (ROPA.includes(slug))        return <RopaPanel atributos={atributos} />
  if (slug === 'libros')          return <LibrosPanel atributos={atributos} />
  if (slug === 'alimentos')       return <AlimentosPanel atributos={atributos} />
  return <GenericPanel atributos={atributos} />
}
