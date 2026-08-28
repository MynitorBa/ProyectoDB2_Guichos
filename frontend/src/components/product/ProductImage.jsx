import { useState } from 'react'
import {
  Monitor, Smartphone, Headphones, Shirt, Layers,
  ShoppingBag, BookOpen, Apple, Home, Dumbbell, Wrench, Gamepad2, Package,
} from 'lucide-react'
import { cn } from '../../lib/utils'

const CATEGORY_CONFIG = {
  computadoras: { Icon: Monitor,     label: 'Computadora', bg: 'from-blue-50 to-indigo-100',    icon: 'text-indigo-400' },
  celulares:    { Icon: Smartphone,  label: 'Celular',     bg: 'from-violet-50 to-purple-100',  icon: 'text-purple-400' },
  audio:        { Icon: Headphones,  label: 'Audio',       bg: 'from-indigo-50 to-blue-100',    icon: 'text-blue-400'   },
  camisas:      { Icon: Shirt,       label: 'Ropa',        bg: 'from-rose-50 to-pink-100',      icon: 'text-pink-400'   },
  pantalones:   { Icon: Layers,      label: 'Ropa',        bg: 'from-slate-50 to-gray-100',     icon: 'text-gray-400'   },
  calzado:      { Icon: ShoppingBag, label: 'Calzado',     bg: 'from-orange-50 to-amber-100',   icon: 'text-amber-400'  },
  libros:       { Icon: BookOpen,    label: 'Libro',       bg: 'from-emerald-50 to-teal-100',   icon: 'text-teal-400'   },
  alimentos:    { Icon: Apple,       label: 'Alimento',    bg: 'from-lime-50 to-green-100',     icon: 'text-green-400'  },
  hogar:        { Icon: Home,        label: 'Hogar',       bg: 'from-amber-50 to-yellow-100',   icon: 'text-yellow-500' },
  deportes:     { Icon: Dumbbell,    label: 'Deporte',     bg: 'from-cyan-50 to-sky-100',       icon: 'text-sky-400'    },
  herramientas: { Icon: Wrench,      label: 'Herramienta', bg: 'from-zinc-50 to-slate-100',     icon: 'text-slate-400'  },
  juguetes:     { Icon: Gamepad2,    label: 'Juguete',     bg: 'from-yellow-50 to-orange-100',  icon: 'text-orange-400' },
}

const DEFAULT_CAT = { Icon: Package, label: 'Producto', bg: 'from-gray-50 to-slate-100', icon: 'text-slate-400' }

function ImageFallback({ categoria, nombre, size = 'md' }) {
  const slug = typeof categoria === 'object' ? categoria?.slug : categoria
  const cfg = CATEGORY_CONFIG[slug] || DEFAULT_CAT
  const { Icon } = cfg
  const iconSizes = { sm: 28, md: 44, lg: 64 }
  return (
    <div className={cn('w-full h-full flex flex-col items-center justify-center gap-2 bg-gradient-to-br', cfg.bg)}>
      <Icon size={iconSizes[size]} className={cfg.icon} strokeWidth={1.5} />
      {nombre && (
        <span className={cn('text-xs font-sans font-medium text-center px-2 line-clamp-2', cfg.icon)}>
          {nombre}
        </span>
      )}
    </div>
  )
}

// Imagen de producto con fallback automático por categoría si src está vacío o falla la carga
export function ProductImage({ src, alt, categoria, nombre, className, aspectRatio = 'aspect-square', size = 'md' }) {
  const [error, setError] = useState(false)
  const hasImage = src && !error

  return (
    <div className={cn('relative overflow-hidden', aspectRatio, className)}>
      {hasImage ? (
        <img
          src={src}
          alt={alt || nombre || 'Producto'}
          loading="lazy"
          onError={() => setError(true)}
          className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
        />
      ) : (
        <ImageFallback categoria={categoria} nombre={nombre} size={size} />
      )}
    </div>
  )
}
