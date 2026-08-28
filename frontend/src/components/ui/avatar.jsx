// Componente de avatar circular con imagen, fallback de iniciales y soporte para tamaños sm/md/lg
import * as AvatarPrimitive from '@radix-ui/react-avatar'
import { cn } from '../../lib/utils'

export function Avatar({ className, size = 'md', ...props }) {
  const sizes = { sm: 'h-8 w-8 text-xs', md: 'h-10 w-10 text-sm', lg: 'h-12 w-12 text-base' }
  return (
    <AvatarPrimitive.Root
      className={cn(
        'relative inline-flex shrink-0 overflow-hidden rounded-full',
        sizes[size],
        className
      )}
      {...props}
    />
  )
}

export function AvatarImage({ className, ...props }) {
  return <AvatarPrimitive.Image className={cn('h-full w-full object-cover', className)} {...props} />
}

export function AvatarFallback({ className, ...props }) {
  return (
    <AvatarPrimitive.Fallback
      className={cn(
        'flex h-full w-full items-center justify-center',
        'bg-[var(--color-action)]/10 text-[var(--color-action)] font-display font-semibold',
        className
      )}
      {...props}
    />
  )
}
