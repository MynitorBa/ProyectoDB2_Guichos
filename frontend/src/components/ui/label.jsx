import * as LabelPrimitive from '@radix-ui/react-label'
import { cn } from '../../lib/utils'

export function Label({ className, ...props }) {
  return (
    <LabelPrimitive.Root
      className={cn(
        'block font-sans text-sm font-medium text-[var(--color-text-primary)] mb-1.5',
        'peer-disabled:opacity-50 peer-disabled:cursor-not-allowed',
        className
      )}
      {...props}
    />
  )
}
