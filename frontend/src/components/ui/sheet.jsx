// Panel deslizante (drawer) accesible desde cualquier lado (right/left/bottom), basado en Radix Dialog
import { forwardRef } from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { cn } from '../../lib/utils'

const Sheet = DialogPrimitive.Root
const SheetTrigger = DialogPrimitive.Trigger
const SheetClose = DialogPrimitive.Close

const SheetOverlay = forwardRef(function SheetOverlay({ className, ...props }, ref) {
  return (
    <DialogPrimitive.Overlay
      ref={ref}
      className={cn(
        'fixed inset-0 z-50 bg-black/40 backdrop-blur-sm',
        'data-[state=open]:animate-in data-[state=closed]:animate-out',
        'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
        className
      )}
      {...props}
    />
  )
})

const SheetContent = forwardRef(function SheetContent(
  { className, side = 'right', title, children, ...props }, ref
) {
  const sideClasses = {
    right: 'right-0 top-0 h-full w-full max-w-sm data-[state=open]:slide-in-from-right data-[state=closed]:slide-out-to-right',
    left:  'left-0 top-0 h-full w-full max-w-sm data-[state=open]:slide-in-from-left data-[state=closed]:slide-out-to-left',
    bottom:'bottom-0 left-0 w-full max-h-[90vh] data-[state=open]:slide-in-from-bottom data-[state=closed]:slide-out-to-bottom',
  }
  return (
    <DialogPrimitive.Portal>
      <SheetOverlay />
      <DialogPrimitive.Content
        ref={ref}
        className={cn(
          'fixed z-50 bg-[var(--color-surface)] shadow-[var(--shadow-xl)]',
          'data-[state=open]:animate-in data-[state=closed]:animate-out duration-300',
          sideClasses[side],
          className
        )}
        {...props}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--color-border)]">
          {title && (
            <DialogPrimitive.Title className="font-display font-semibold text-base text-[var(--color-text-primary)]">
              {title}
            </DialogPrimitive.Title>
          )}
          <SheetClose className="ml-auto p-1 rounded-[var(--radius-md)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-border)] transition-colors">
            <X size={18} />
          </SheetClose>
        </div>
        <div className="overflow-y-auto h-[calc(100%-57px)]">
          {children}
        </div>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  )
})

export { Sheet, SheetTrigger, SheetClose, SheetContent }
