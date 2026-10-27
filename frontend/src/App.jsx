import { BrowserRouter, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import Router from './router'
import { Header } from './components/layout/Header'
import { Footer } from './components/layout/Footer'
import { AvisoServicios } from './components/layout/AvisoServicios'
import { ErrorBoundary } from './components/ErrorBoundary'

// Un error en una página no tumba la cabecera; al cambiar de ruta se reintenta solo.
function ContenidoProtegido() {
  const { pathname } = useLocation()
  return (
    <ErrorBoundary resetKey={pathname}>
      <Router />
    </ErrorBoundary>
  )
}

function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => { window.scrollTo({ top: 0, left: 0, behavior: 'instant' }) }, [pathname])
  return null
}

// Shell principal: envuelve en BrowserRouter y compone Header + contenido de ruta + Footer
export default function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ScrollToTop />
      <div className="min-h-screen flex flex-col bg-[var(--color-background)]">
        <ErrorBoundary>
          <Header />
        </ErrorBoundary>
        <ErrorBoundary fallback={null}>
          <AvisoServicios />
        </ErrorBoundary>
        <main className="flex-1">
          <ContenidoProtegido />
        </main>
        <Footer />
      </div>
    </BrowserRouter>
  )
}
