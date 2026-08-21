import { useState } from 'react'
import { cn } from '../../lib/utils'

const CATEGORY_CONFIG = {
  computadoras: { emoji: '💻', label: 'Computadora', bg: 'from-blue-50 to-indigo-100', text: 'text-indigo-400' },
  celulares:    { emoji: '📱', label: 'Celular',      bg: 'from-violet-50 to-purple-100', text: 'text-purple-400' },
  audio:        { emoji: '🎧', label: 'Audio',        bg: 'from-indigo-50 to-blue-100',  text: 'text-blue-400' },
  camisas:      { emoji: '👕', label: 'Ropa',         bg: 'from-rose-50 to-pink-100',    text: 'text-pink-400' },
  pantalones:   { emoji: '👖', label: 'Ropa',         bg: 'from-slate-50 to-gray-100',   text: 'text-gray-400' },
  calzado:      { emoji: '👟', label: 'Calzado',      bg: 'from-orange-50 to-amber-100', text: 'text-amber-400' },
  libros:       { emoji: '📚', label: 'Libro',        bg: 'from-emerald-50 to-teal-100', text: 'text-teal-400' },
  alimentos:    { emoji: '🥗', label: 'Alimento',     bg: 'from-lime-50 to-green-100',   text: 'text-green-400' },
  hogar:        { emoji: '🏠', label: 'Hogar',        bg: 'from-amber-50 to-yellow-100', text: 'text-yellow-500' },
  deportes:     { emoji: '⚽', label: 'Deporte',      bg: 'from-cyan-50 to-sky-100',     text: 'text-sky-400' },
  herramientas: { emoji: '🔧', label: 'Herramienta',  bg: 'from-zinc-50 to-slate-100',   text: 'text-slate-400' },
  juguetes:     { emoji: '🧸', label: 'Juguete',      bg: 'from-yellow-50 to-orange-100',text: 'text-orange-400' },
}

const DEFAULT_CAT = { emoji: '📦', label: 'Producto', bg: 'from-gray-50 to-slate-100', text: 'text-slate-400' }

function ImageFallback({ categoria, nombre, size = 'md' }) {
  const slug = typeof categoria === 'object' ? categoria?.slug : categoria
  const cfg = CATEGORY_CONFIG[slug] || DEFAULT_CAT
  const emojiSizes = { sm: 'text-3xl', md: 'text-5xl', lg: 'text-7xl' }
  return (
    <div className={cn('w-full h-full flex flex-col items-center justify-center gap-2 bg-gradient-to-br', cfg.bg)}>
      <span className={emojiSizes[size]}>{cfg.emoji}</span>
      {nombre && (
        <span className={cn('text-xs font-sans font-medium text-center px-2 line-clamp-2', cfg.text)}>
          {nombre}
        </span>
      )}
    </div>
  )
}

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
