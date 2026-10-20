import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import App from './App'
import './index.css'
import { AuthProvider } from './context/AuthContext'
import { CartProvider } from './context/CartContext'
import { queryClient } from './lib/queryClient'
import { ErrorBoundary } from './components/ErrorBoundary'
import { instalarCapturaGlobal, instalarToastSeguro } from './lib/toastSeguro'

// Antes de montar: los avisos solo aceptan texto y las promesas rechazadas sin
// manejar se muestran al usuario en lugar de fallar en silencio.
instalarToastSeguro()
instalarCapturaGlobal()

// Punto de entrada: monta la app con los providers globales (React Query, Auth, Cart) y el sistema de toasts
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary pantallaCompleta>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <CartProvider>
            <App />
            {/* Si un aviso fallara al dibujarse, solo se pierde el aviso, no la página. */}
            <ErrorBoundary fallback={null}>
              <Toaster
                position="bottom-right"
                toastOptions={{
                  style: {
                    background: 'var(--color-surface)',
                    color: 'var(--color-text-primary)',
                    border: '1px solid var(--color-border)',
                    borderRadius: 'var(--radius-lg)',
                    fontFamily: 'var(--font-sans)',
                    fontSize: '14px',
                  },
                }}
              />
            </ErrorBoundary>
          </CartProvider>
        </AuthProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>
)
