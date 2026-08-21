import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Navbar() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()

  const handleSignOut = () => {
    signOut()
    navigate('/login')
  }

  return (
    <nav>
      <Link to="/" style={{ fontWeight: 700, fontSize: '1.1rem' }}>TiendaYa</Link>
      <Link to="/">Catálogo</Link>
      {user && <Link to="/cart">Carrito</Link>}
      {user && <Link to="/orders">Mis pedidos</Link>}
      {user?.roles?.includes('administrador') && <Link to="/admin">Admin</Link>}
      <span className="spacer" />
      {user ? (
        <>
          <span style={{ fontSize: '.85rem' }}>{user.nombre} ({user.roles?.join(', ')})</span>
          <button className="btn" onClick={handleSignOut} style={{ color: '#fff', background: 'transparent', border: '1px solid #fff' }}>
            Salir
          </button>
        </>
      ) : (
        <>
          <Link to="/login">Login</Link>
          <Link to="/register">Registrarse</Link>
        </>
      )}
    </nav>
  )
}
