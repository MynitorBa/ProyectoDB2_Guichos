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
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ScrollToTop />
      <div className="min-h-screen flex flex-col bg-[var(--color-background)]">
        <Header />
        <main className="flex-1">
          <Router />
        </main>
        <Footer />
      </div>
    </BrowserRouter>
  )
}
