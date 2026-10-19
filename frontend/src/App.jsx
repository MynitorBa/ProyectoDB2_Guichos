import { BrowserRouter, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import Router from './router'
import { Header } from './components/layout/Header'
import { Footer } from './components/layout/Footer'

function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => { window.scrollTo({ top: 0, left: 0, behavior: 'instant' }) }, [pathname])
  return null
}

// Shell principal: envuelve en BrowserRouter y compone Header + contenido de ruta + Footer
export default function App() {
  const demoMode = import.meta.env.VITE_DEMO_MODE === 'true'
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ScrollToTop />
      <div className="min-h-screen flex flex-col bg-[var(--color-background)]">
        {demoMode && (
          <div className="bg-amber-400 text-amber-950 text-center text-xs sm:text-sm font-bold tracking-wide px-4 py-2">
            TiendaYa — DEMO / DATOS SINTÉTICOS
          </div>
        )}
        <Header />
        <main className="flex-1">
          <Router />
        </main>
        <Footer />
      </div>
    </BrowserRouter>
  )
}
