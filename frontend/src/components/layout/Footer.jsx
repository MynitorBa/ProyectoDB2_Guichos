import { Link } from 'react-router-dom'
import { Shield, Truck, RefreshCw } from 'lucide-react'

export function Footer() {
  return (
    <footer className="border-t border-[var(--color-border)] bg-[var(--color-surface)] mt-16">
      {/* Señales de confianza */}
      <div className="max-w-[1280px] mx-auto px-4 md:px-6 py-8">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 pb-8 border-b border-[var(--color-border)]">
          {[
            { icon: Truck,     title: 'Envío a todo Guatemala',  desc: 'Departamentos y municipios' },
            { icon: Shield,    title: 'Pago 100% seguro',        desc: 'Tarjeta, débito o transferencia' },
            { icon: RefreshCw, title: 'Devoluciones fáciles',    desc: 'Hasta 15 días después de recibir' },
          ].map(({ icon: Icon, title, desc }) => (
            <div key={title} className="flex items-center gap-4">
              <div className="h-10 w-10 shrink-0 rounded-[var(--radius-md)] bg-[var(--color-action)]/10 flex items-center justify-center">
                <Icon size={18} className="text-[var(--color-action)]" />
              </div>
              <div>
                <p className="font-display font-semibold text-sm text-[var(--color-text-primary)]">{title}</p>
                <p className="font-sans text-xs text-[var(--color-text-muted)]">{desc}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="pt-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="h-6 w-6 rounded-[var(--radius-sm)] bg-[var(--color-action)] flex items-center justify-center">
              <span className="font-display font-bold text-white text-xs">T</span>
            </div>
            <span className="font-display font-bold text-[var(--color-text-primary)]">TiendaYa</span>
            <span className="font-sans text-xs text-[var(--color-text-muted)]">— Marketplace guatemalteco</span>
          </div>
          <p className="font-sans text-xs text-[var(--color-text-muted)]">
            © {new Date().getFullYear()} TiendaYa · Proyecto académico UNIS
          </p>
        </div>
      </div>
    </footer>
  )
}
