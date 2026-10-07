import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...entradas) {
  return twMerge(clsx(entradas))
}

const BOTON = {
  primary: 'bg-[var(--color-action)] text-white hover:bg-[var(--color-action-h)]',
  secondary: 'bg-[var(--color-surface)] text-[var(--color-text-primary)] border border-[var(--color-border)] hover:border-[var(--color-border-strong)]',
  ghost: 'text-[var(--color-text-secondary)] hover:bg-[var(--color-border)]',
}

export function Boton({ variante = 'primary', cargando = false, className, children, ...props }) {
  return (
    <button
      type="button"
      className={cn('inline-flex items-center justify-center gap-1.5 h-8 px-3 rounded-md text-sm font-semibold transition-colors disabled:opacity-50 disabled:pointer-events-none', BOTON[variante], className)}
      disabled={cargando || props.disabled}
      {...props}
    >
      {cargando && <span className="h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" />}
      {children}
    </button>
  )
}

const ETIQUETA = {
  default: 'bg-[var(--color-border)] text-[var(--color-text-secondary)]',
  action: 'bg-[var(--color-action)]/10 text-[var(--color-action)]',
  success: 'bg-[var(--color-success-light)] text-[var(--color-success)]',
  warning: 'bg-[var(--color-warning-light)] text-[var(--color-warning)]',
  error: 'bg-[var(--color-error-light)] text-[var(--color-error)]',
}

export function Etiqueta({ tono = 'default', className, children }) {
  return <span className={cn('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium', ETIQUETA[tono], className)}>{children}</span>
}

export function Cargando({ className }) {
  return <div className={cn('animate-pulse rounded-md bg-[var(--color-border)]', className)} />
}

export function Panel({ titulo, descripcion, icono: Icono, acciones, children, className }) {
  return (
    <section className={cn('bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl p-5', className)}>
      <header className="flex items-start justify-between gap-3 mb-4 flex-wrap">
        <div className="flex gap-2.5">
          {Icono && <Icono size={18} className="text-[var(--color-action)] mt-0.5 shrink-0" />}
          <div>
            <h2 className="font-semibold text-[15px]">{titulo}</h2>
            {descripcion && <p className="text-xs text-[var(--color-text-muted)] mt-0.5 max-w-xl">{descripcion}</p>}
          </div>
        </div>
        {acciones && <div className="flex gap-2 flex-wrap">{acciones}</div>}
      </header>
      {children}
    </section>
  )
}

// El backend guarda fechas UTC sin zona; se muestran en hora local.
export function horaLocal(iso) {
  if (!iso) return '—'
  const fecha = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`)
  return fecha.toLocaleTimeString('es-GT', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function duracion(segundos) {
  if (segundos == null) return '—'
  if (segundos < 60) return `${Math.round(segundos)} s`
  if (segundos < 3600) return `${Math.round(segundos / 60)} min`
  return `${(segundos / 3600).toFixed(1)} h`
}
