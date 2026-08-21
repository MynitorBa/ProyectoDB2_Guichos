import { forwardRef } from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva } from 'class-variance-authority'
import { cn } from '../../lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 font-display font-semibold transition-all duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-action)] disabled:opacity-50 disabled:pointer-events-none select-none',
  {
    variants: {
      variant: {
        primary:
          'bg-[var(--color-action)] text-white hover:bg-[var(--color-action-h)] active:scale-[.98] shadow-sm',
        secondary:
          'bg-[var(--color-surface)] text-[var(--color-text-primary)] border border-[var(--color-border)] hover:bg-[var(--color-background)] hover:border-[var(--color-border-strong)]',
        ghost:
          'text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] hover:text-[var(--color-text-primary)]',
        jade:
          'bg-[var(--color-jade)] text-white hover:opacity-90 active:scale-[.98] shadow-sm',
        destructive:
          'bg-[var(--color-error)] text-white hover:opacity-90 active:scale-[.98]',
        link:
          'text-[var(--color-action)] underline-offset-4 hover:underline p-0 h-auto',
      },
      size: {
        sm:  'h-8  px-3 text-sm rounded-[var(--radius-md)]',
        md:  'h-10 px-4 text-sm rounded-[var(--radius-md)]',
        lg:  'h-12 px-6 text-base rounded-[var(--radius-md)]',
        xl:  'h-14 px-8 text-base rounded-[var(--radius-lg)]',
        icon:'h-10 w-10 rounded-[var(--radius-md)]',
        'icon-sm': 'h-8 w-8 rounded-[var(--radius-md)]',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  }
)

const Button = forwardRef(function Button(
  { className, variant, size, asChild = false, loading = false, children, ...props },
  ref
) {
  const Comp = asChild ? Slot : 'button'
  return (
    <Comp
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      disabled={loading || props.disabled}
      {...props}
    >
      {asChild ? children : (
        <>
          {loading && (
            <svg className="animate-spin h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeDasharray="32" strokeDashoffset="12" strokeLinecap="round"/>
            </svg>
          )}
          {children}
        </>
      )}
    </Comp>
  )
})

export { Button, buttonVariants }
