import { Link } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { Badge } from './ui/badge'

const NIVEL = {
  muy_probable: { etiqueta: 'Muy probable', variante: 'error' },
  posible: { etiqueta: 'Posible', variante: 'warning' },
}

// Aviso de posibles duplicados (similitud por vectores y por nombre); nunca bloquea la solicitud.
export function PossibleDuplicates({ items, titulo, ayuda }) {
  if (!items?.length) return null
  return (
    <div role="status" className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-amber-900">
      <p className="flex items-center gap-2 text-sm font-semibold">
        <AlertTriangle size={15} className="shrink-0" /> {titulo}
      </p>
      <ul className="mt-2 space-y-1.5">
        {items.map(item => (
          <li key={item.producto_ref} className="flex flex-wrap items-center gap-2 text-sm">
            <Badge variant={NIVEL[item.nivel]?.variante || 'warning'}>{NIVEL[item.nivel]?.etiqueta || item.nivel}</Badge>
            <Link to={`/products/${item.producto_ref}`} target="_blank" className="font-medium underline">
              {item.nombre}
            </Link>
            <span className="font-mono text-xs opacity-70">{item.sku}</span>
            <span className="text-xs opacity-70">· {Math.round(Math.max(item.similitud, item.parecido_nombre) * 100)} % parecido</span>
          </li>
        ))}
      </ul>
      {ayuda && <p className="mt-2 text-xs">{ayuda}</p>}
    </div>
  )
}
