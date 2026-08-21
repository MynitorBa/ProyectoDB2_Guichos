import { BrowserRouter } from 'react-router-dom'
import Router from './router'
import { Header } from './components/layout/Header'
import { Footer } from './components/layout/Footer'

export default function App() {
  return (
    <BrowserRouter>
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
