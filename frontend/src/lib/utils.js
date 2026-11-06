import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

// cn: combina clases condicionales (clsx) y resuelve conflictos de Tailwind (twMerge)
export function cn(...inputs) {
  return twMerge(clsx(inputs))
}

// formatQ: formatea un número como precio en quetzales con 2 decimales y separadores guatemaltecos
export function formatQ(amount) {
  const n = Number(amount)
  if (isNaN(n)) return 'Q0.00'
  return `Q${n.toLocaleString('es-GT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function formatDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('es-GT', {
    year: 'numeric', month: 'long', day: 'numeric',
    timeZone: 'America/Guatemala',
  })
}

export function formatDatetime(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleString('es-GT', {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
    timeZone: 'America/Guatemala',
  })
}

export function slugify(str) {
  return str.toLowerCase().replace(/\s+/g, '-').replace(/[^\w-]/g, '')
}

// Formato de slug de categoría mientras se escribe: minúsculas sin tildes,
// números y guiones simples ("Ropa Deportiva" → "ropa-deportiva"). Deja un
// guion final para poder seguir escribiendo; `limpiarSlug` lo quita al terminar.
export const SLUG_PATRON = '[a-z0-9]+(-[a-z0-9]+)*'
export function formatearSlug(str = '') {
  return str.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[\s_]+/g, '-').replace(/[^a-z0-9-]/g, '')
    .replace(/-{2,}/g, '-').replace(/^-/, '').slice(0, 120)
}
export function limpiarSlug(str = '') {
  return formatearSlug(str).replace(/-+$/, '')
}

// Prefijo SKU: exactamente 3 letras mayúsculas (los SKU quedan como LAP-1A2B3C4D).
export const PREFIJO_SKU_PATRON = '[A-Z]{3}'
export function formatearPrefijoSku(str = '') {
  return str.normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[^a-zA-Z]/g, '').toUpperCase().slice(0, 3)
}
