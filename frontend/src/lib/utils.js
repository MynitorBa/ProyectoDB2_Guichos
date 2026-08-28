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
