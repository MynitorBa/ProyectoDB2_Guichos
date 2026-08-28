// Select con búsqueda integrada en el dropdown (normaliza acentos) y animaciones de apertura/cierre
import React, { useEffect, useRef, useState } from 'react'
import * as SelectPrimitive from '@radix-ui/react-select'
import { ChevronDown, Check, Search } from 'lucide-react'
import { cn } from '../../lib/utils'

const Select = SelectPrimitive.Root
const SelectValue = SelectPrimitive.Value
const SelectGroup = SelectPrimitive.Group

function SelectTrigger({ className, children, ...props }) {
  return (
    <SelectPrimitive.Trigger
      className={cn(
        'flex h-10 w-full items-center justify-between gap-2 px-3',
        'bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-md)]',
        'font-sans text-sm text-[var(--color-text-primary)]',
        'hover:border-[var(--color-border-strong)] transition-colors',
        'focus:outline-none focus:border-[var(--color-action)] focus:ring-2 focus:ring-[var(--color-action)]/20',
        'data-[placeholder]:text-[var(--color-text-muted)]',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        className
      )}
      {...props}
    >
      {children}
      <SelectPrimitive.Icon>
        <ChevronDown size={14} className="text-[var(--color-text-muted)] shrink-0" />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  )
}

function nodeText(node) {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(nodeText).join(' ')
  if (React.isValidElement(node)) return nodeText(node.props.children)
  return ''
}

function normalizeSearch(value) {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
}

function SelectContent({ className, children, position = 'popper', searchPlaceholder = 'Buscar...', ...props }) {
  const [query, setQuery] = useState('')
  const inputRef = useRef(null)
  useEffect(() => {
    const timer = setTimeout(() => inputRef.current?.focus(), 0)
    return () => clearTimeout(timer)
  }, [])
  const normalizedQuery = normalizeSearch(query.trim())
  const filteredChildren = React.Children.toArray(children).filter(child => (
    !normalizedQuery || normalizeSearch(nodeText(child)).includes(normalizedQuery)
  ))
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content
        position={position}
        sideOffset={4}
        className={cn(
          'relative z-50 min-w-[8rem] overflow-hidden',
          'bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] shadow-[var(--shadow-lg)]',
          'data-[state=open]:animate-in data-[state=closed]:animate-out',
          'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
          'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
          'data-[side=bottom]:slide-in-from-top-2',
          className
        )}
        {...props}
      >
        <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-2">
          <Search size={14} className="shrink-0 text-[var(--color-text-muted)]" />
          <input
            ref={inputRef}
            value={query}
            onChange={event => setQuery(event.target.value)}
            onKeyDown={event => {
              if (event.key !== 'Escape') event.stopPropagation()
            }}
            placeholder={searchPlaceholder}
            aria-label={searchPlaceholder}
            className="min-w-0 flex-1 bg-transparent text-sm text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-muted)]"
          />
        </div>
        <SelectPrimitive.Viewport className="max-h-60 overflow-y-auto p-1 [scrollbar-width:thin]">
          {filteredChildren.length > 0 ? filteredChildren : (
            <div className="px-3 py-6 text-center text-sm text-[var(--color-text-muted)]">
              Sin resultados
            </div>
          )}
        </SelectPrimitive.Viewport>
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  )
}

function SelectItem({ className, children, ...props }) {
  return (
    <SelectPrimitive.Item
      className={cn(
        'relative flex cursor-pointer select-none items-center gap-2 rounded-[var(--radius-md)] px-3 py-2',
        'font-sans text-sm text-[var(--color-text-primary)]',
        'hover:bg-[var(--color-background)] transition-colors',
        'focus:bg-[var(--color-background)] focus:outline-none',
        'data-[disabled]:opacity-50 data-[disabled]:pointer-events-none',
        className
      )}
      {...props}
    >
      <SelectPrimitive.ItemIndicator>
        <Check size={14} className="text-[var(--color-action)]" />
      </SelectPrimitive.ItemIndicator>
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
    </SelectPrimitive.Item>
  )
}

function SelectLabel({ className, ...props }) {
  return (
    <SelectPrimitive.Label
      className={cn('px-3 py-1.5 text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider', className)}
      {...props}
    />
  )
}

export { Select, SelectTrigger, SelectValue, SelectContent, SelectItem, SelectGroup, SelectLabel }
