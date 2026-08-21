import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { login, me } from '../api/auth'
import { useAuth } from '../context/AuthContext'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { signIn } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data } = await login(email, password)
      localStorage.setItem('token', data.access_token)
      const { data: userData } = await me()
      signIn(data.access_token, userData)
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al iniciar sesión.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: 400, margin: '4rem auto' }}>
      <div className="card">
        <h2 style={{ marginBottom: '1.5rem' }}>Iniciar sesión</h2>
        {error && <div className="alert alert-error">{error}</div>}
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div className="form-group">
            <label>Contraseña</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          <button className="btn btn-primary" type="submit" disabled={loading} style={{ width: '100%' }}>
            {loading ? 'Ingresando...' : 'Ingresar'}
          </button>
        </form>
        <p style={{ marginTop: '1rem', textAlign: 'center' }}>
          ¿No tienes cuenta? <Link to="/register">Regístrate</Link>
        </p>
        <p style={{ marginTop: '.5rem', fontSize: '.8rem', color: '#6c757d', textAlign: 'center' }}>
          Admin: admin@tiendaya.gt / password123
        </p>
      </div>
    </div>
  )
}
