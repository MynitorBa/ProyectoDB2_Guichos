import { Link } from 'react-router-dom'

export function Footer() {
  return (
    <footer className="border-t border-[var(--color-border)] bg-[var(--color-surface)] mt-16">
      <div className="max-w-[1280px] mx-auto px-4 md:px-6 py-8">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
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
