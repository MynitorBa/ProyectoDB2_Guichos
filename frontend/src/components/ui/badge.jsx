import { cva } from 'class-variance-authority'
import { cn } from '../../lib/utils'

const badgeVariants = cva(
  'inline-flex items-center gap-1 font-sans font-medium rounded-[var(--radius-full)] border',
  {
    variants: {
      variant: {
        default:     'bg-[var(--color-border)] text-[var(--color-text-secondary)] border-transparent text-xs px-2.5 py-0.5',
        jade:        'bg-[var(--color-jade-light)] text-[var(--color-jade)] border-transparent text-xs px-2.5 py-0.5',
        action:      'bg-[var(--color-action)]/10 text-[var(--color-action)] border-transparent text-xs px-2.5 py-0.5',
        success:     'bg-[var(--color-success-light)] text-[var(--color-success)] border-transparent text-xs px-2.5 py-0.5',
        warning:     'bg-[var(--color-warning-light)] text-[var(--color-warning)] border-transparent text-xs px-2.5 py-0.5',
        error:       'bg-[var(--color-error-light)] text-[var(--color-error)] border-transparent text-xs px-2.5 py-0.5',
        outline:     'bg-transparent text-[var(--color-text-secondary)] border-[var(--color-border)] text-xs px-2.5 py-0.5',
      },
    },
    defaultVariants: { variant: 'default' },
  }
)

export function Badge({ className, variant, children, ...props }) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props}>
      {children}
    </span>
  )
}
