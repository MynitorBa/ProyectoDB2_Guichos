import { Component } from 'react'
import { AlertTriangle, Home, RotateCw } from 'lucide-react'

// Atrapa errores de renderizado para que un fallo en una sección no deje la
// pantalla en blanco. `resetKey` (por ejemplo, la ruta actual) lo reinicia
// automáticamente al navegar a otra página.
export class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('Error de interfaz atrapado:', error, info?.componentStack)
  }

  componentDidUpdate(prevProps) {
    if (this.state.error && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null })
    }
  }

  render() {
    if (!this.state.error) return this.props.children
    if ('fallback' in this.props) return this.props.fallback
    const completa = this.props.pantallaCompleta
    return (
      <div
        role="alert"
        className={
          completa
            ? 'min-h-screen flex items-center justify-center p-6 bg-[var(--color-background)]'
            : 'flex items-center justify-center px-4 py-16'
        }
      >
        <div className="max-w-md w-full text-center rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-8 shadow-sm">
          <AlertTriangle className="mx-auto mb-3 text-[var(--color-warning)]" size={36} aria-hidden="true" />
          <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">Algo salió mal en esta sección</h2>
          <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
            Ocurrió un problema al mostrar esta página. Tus datos están a salvo; puedes intentarlo de nuevo o volver al inicio.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <button
              type="button"
              onClick={() => this.setState({ error: null })}
              className="inline-flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--color-action)] px-4 py-2 text-sm font-medium text-white hover:opacity-90"
            >
              <RotateCw size={15} aria-hidden="true" /> Reintentar
            </button>
            <a
              href="/"
              className="inline-flex items-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-border)] px-4 py-2 text-sm font-medium text-[var(--color-text-primary)] hover:bg-[var(--color-border)]"
            >
              <Home size={15} aria-hidden="true" /> Ir al inicio
            </a>
          </div>
        </div>
      </div>
    )
  }
}
