import { BrowserRouter } from 'react-router-dom'
import Router from './router'
import Navbar from './components/Navbar'

export default function App() {
  return (
    <BrowserRouter>
      <Navbar />
      <main style={{ padding: '1rem', maxWidth: 1200, margin: '0 auto' }}>
        <Router />
      </main>
    </BrowserRouter>
  )
}
