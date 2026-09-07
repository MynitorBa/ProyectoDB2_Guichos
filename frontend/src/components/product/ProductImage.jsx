import { useState, useEffect } from 'react'
import { cn } from '../../lib/utils'

// Mapeo de categoría → query de Unsplash-compatible seed para picsum
const CATEGORY_SEEDS = {
  computadoras: 'laptop-computer',
  celulares:    'smartphone-phone',
  audio:        'headphones-audio',
  camisas:      'shirt-clothing',
  pantalones:   'pants-fashion',
  calzado:      'shoes-footwear',
  libros:       'book-reading',
  alimentos:    'food-grocery',
  hogar:        'home-decor',
  deportes:     'sports-fitness',
  herramientas: 'tools-hardware',
  juguetes:     'toys-games',
}

function slugify(str = '') {
  return str.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 40)
}

function getPicsumSrc(nombre, categoria) {
  const catSlug = typeof categoria === 'object' ? categoria?.slug : categoria
  const catSeed = CATEGORY_SEEDS[catSlug]
  const seed = catSeed ? `${catSeed}-${slugify(nombre)}` : slugify(nombre) || 'product'
  return `https://picsum.photos/seed/${seed}/600/600`
}

export function ProductImage({ src, alt, categoria, nombre, className, aspectRatio = 'aspect-square', size = 'md' }) {
  const picsumSrc = getPicsumSrc(nombre, categoria)
  const [imgSrc, setImgSrc] = useState(src || picsumSrc)
  const [usedFallback, setUsedFallback] = useState(false)

  useEffect(() => {
    setImgSrc(src || picsumSrc)
    setUsedFallback(false)
  }, [src, picsumSrc])

  function handleError() {
    if (!usedFallback) {
      setUsedFallback(true)
      setImgSrc(picsumSrc)
    }
  }

  return (
    <div className={cn('relative overflow-hidden', aspectRatio, className)}>
      <img
        src={imgSrc}
        alt={alt || nombre || 'Producto'}
        loading="lazy"
        onError={handleError}
        className="w-full h-full object-cover"
      />
    </div>
  )
}
