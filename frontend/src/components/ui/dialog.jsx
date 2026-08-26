import { forwardRef } from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { cn } from '../../lib/utils'

const Dialog = DialogPrimitive.Root
const DialogTrigger = DialogPrimitive.Trigger
const DialogPortal = DialogPrimitive.Portal
const DialogClose = DialogPrimitive.Close

const DialogOverlay = forwardRef(function DialogOverlay({ className, ...props }, ref) {
  return (
    <DialogPrimitive.Overlay
      ref={ref}
      className={cn(
        'fixed inset-0 z-50 bg-black/50 backdrop-blur-sm',
        'data-[state=open]:animate-in data-[state=closed]:animate-out',
        'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
        className
      )}
      {...props}
    />
  )
})

const DialogContent = forwardRef(function DialogContent(
  { className, children, showClose = true, ...props }, ref
) {
  return (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Content
        ref={ref}
        className={cn(
          'fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2',
          'w-full max-w-lg bg-[var(--color-surface)] rounded-[var(--radius-xl)] shadow-[var(--shadow-xl)]',
          'p-6',
          'data-[state=open]:animate-in data-[state=closed]:animate-out',
          'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
          'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
          'data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-1/2',
          'data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-1/2',
          'max-h-[90vh] overflow-y-auto',
          className
        )}
        {...props}
      >
        {showClose && (
          <DialogClose className="absolute right-4 top-4 p-1 rounded-[var(--radius-md)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-border)] transition-colors">
            <X size={18} />
          </DialogClose>
        )}
        {children}
      </DialogPrimitive.Content>
    </DialogPortal>
  )
})

const DialogTitle = forwardRef(function DialogTitle({ className, ...props }, ref) {
  return (
    <DialogPrimitive.Title
      ref={ref}
      className={cn('font-display font-semibold text-lg text-[var(--color-text-primary)] mb-1', className)}
      {...props}
    />
  )
})

const DialogDescription = forwardRef(function DialogDescription({ className, ...props }, ref) {
  return (
    <DialogPrimitive.Description
      ref={ref}
      className={cn('text-sm text-[var(--color-text-secondary)] mb-4', className)}
      {...props}
    />
  )
})

export { Dialog, DialogTrigger, DialogContent, DialogTitle, DialogDescription, DialogClose }
