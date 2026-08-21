import { Star } from 'lucide-react'
import { cn } from '../../lib/utils'

export function StarRating({ value = 0, max = 5, size = 14, showValue = true, count, className }) {
  return (
    <div className={cn('flex items-center gap-1', className)}>
      <div className="flex items-center gap-0.5">
        {Array.from({ length: max }).map((_, i) => {
          const filled = i < Math.floor(value)
          const partial = !filled && i < value
          return (
            <Star
              key={i}
              size={size}
              className={cn(
                filled || partial ? 'fill-amber-400 text-amber-400' : 'fill-transparent text-[var(--color-border-strong)]'
              )}
            />
          )
        })}
      </div>
      {showValue && (
        <span className="font-sans text-xs text-[var(--color-text-secondary)]">
          {value > 0 ? value.toFixed(1) : ''}
          {count !== undefined && (
            <span className="ml-0.5">({count})</span>
          )}
        </span>
      )}
    </div>
  )
}
