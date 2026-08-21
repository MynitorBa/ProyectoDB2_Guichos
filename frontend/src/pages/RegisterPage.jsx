import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { register, login, me } from '../api/auth'
import { useAuth } from '../context/AuthContext'

export default function RegisterPage() {
  const [form, setForm] = useState({ email: '', password: '', nombre: '', apellido: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { signIn } = useAuth()
  const navigate = useNavigate()

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await register(form)
      const { data } = await login(form.email, form.password)
      localStorage.setItem('token', data.access_token)
      const { data: userData } = await me()
      signIn(data.access_token, userData)
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al registrarse.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: 440, margin: '4rem auto' }}>
      <div className="card">
        <h2 style={{ marginBottom: '1.5rem' }}>Crear cuenta</h2>
        {error && <div className="alert alert-error">{error}</div>}
        <form onSubmit={handleSubmit}>
          {[['nombre', 'Nombre'], ['apellido', 'Apellido'], ['email', 'Email'], ['password', 'Contraseña']].map(([k, lbl]) => (
            <div className="form-group" key={k}>
              <label>{lbl}</label>
              <input type={k === 'password' ? 'password' : k === 'email' ? 'email' : 'text'}
                value={form[k]} onChange={set(k)} required />
            </div>
          ))}
          <button className="btn btn-primary" type="submit" disabled={loading} style={{ width: '100%' }}>
            {loading ? 'Creando cuenta...' : 'Registrarse'}
          </button>
        </form>
        <p style={{ marginTop: '1rem', textAlign: 'center' }}>
          ¿Ya tienes cuenta? <Link to="/login">Ingresar</Link>
        </p>
      </div>
    </div>
  )
}
