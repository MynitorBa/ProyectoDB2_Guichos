// Placeholder animado para estados de carga; ProductCardSkeleton replica la estructura de la tarjeta de producto
import { cn } from '../../lib/utils'

export function Skeleton({ className, ...props }) {
  return (
    <div
      className={cn(
        'animate-pulse rounded-[var(--radius-md)] bg-[var(--color-border)]',
        className
      )}
      {...props}
    />
  )
}

export function ProductCardSkeleton() {
  return (
    <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl overflow-hidden">
      <div className="relative">
        <Skeleton className="aspect-square w-full rounded-none" />
        <Skeleton className="absolute top-2.5 left-2.5 h-4 w-16 rounded-full" />
      </div>
      <div className="px-3.5 pt-3 pb-4 space-y-2">
        <Skeleton className="h-3.5 w-full" />
        <Skeleton className="h-3.5 w-3/4" />
        <div className="pt-2">
          <Skeleton className="h-5 w-1/3" />
        </div>
      </div>
    </div>
  )
}
