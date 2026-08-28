// Campo de texto (Input) y área de texto (Textarea) con estilos del tema, prop error para borde rojo y soporte de ref
import { forwardRef } from 'react'
import { cn } from '../../lib/utils'

const Input = forwardRef(function Input({ className, type = 'text', error, ...props }, ref) {
  return (
    <input
      type={type}
      ref={ref}
      className={cn(
        'w-full h-10 px-3 bg-[var(--color-surface)] text-[var(--color-text-primary)]',
        'border border-[var(--color-border)] rounded-[var(--radius-md)]',
        'font-sans text-sm placeholder:text-[var(--color-text-muted)]',
        'transition-colors duration-150',
        'hover:border-[var(--color-border-strong)]',
        'focus:outline-none focus:border-[var(--color-action)] focus:ring-2 focus:ring-[var(--color-action)]/20',
        error && 'border-[var(--color-error)] focus:border-[var(--color-error)] focus:ring-[var(--color-error)]/20',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        className
      )}
      {...props}
    />
  )
})

const Textarea = forwardRef(function Textarea({ className, error, ...props }, ref) {
  return (
    <textarea
      ref={ref}
      className={cn(
        'w-full px-3 py-2 bg-[var(--color-surface)] text-[var(--color-text-primary)]',
        'border border-[var(--color-border)] rounded-[var(--radius-md)]',
        'font-sans text-sm placeholder:text-[var(--color-text-muted)]',
        'transition-colors duration-150 resize-y min-h-[80px]',
        'hover:border-[var(--color-border-strong)]',
        'focus:outline-none focus:border-[var(--color-action)] focus:ring-2 focus:ring-[var(--color-action)]/20',
        error && 'border-[var(--color-error)]',
        className
      )}
      {...props}
    />
  )
})

export { Input, Textarea }
