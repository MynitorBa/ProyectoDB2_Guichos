import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getProductHistory, getProductStateAt } from '../api/products'

const TIPO_COLOR = {
  PRODUCTO_CREADO: '#0f5132',
  PRECIO_ACTUALIZADO: '#084298',
  DESCRIPCION_ACTUALIZADA: '#5a1e9a',
  DISPONIBILIDAD_CAMBIADA: '#856404',
  ATRIBUTOS_ACTUALIZADOS: '#0f5132',
  PRODUCTO_DESCONTINUADO: '#842029',
}

export default function ProductHistoryPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [historial, setHistorial] = useState([])
  const [estado, setEstado] = useState(null)
  const [fecha, setFecha] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    getProductHistory(id)
      .then((r) => setHistorial(r.data.eventos || []))
      .catch(() => setError('No se pudo cargar el historial.'))
  }, [id])

  const buscarEstado = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const { data } = await getProductStateAt(id, fecha)
      setEstado(data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al reconstruir estado.')
      setEstado(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: '2rem auto' }}>
      <button className="btn btn-secondary" onClick={() => navigate('/admin')} style={{ marginBottom: '1rem' }}>
        ← Panel admin
      </button>
      <h2>Historial de producto</h2>
      <p style={{ color: '#6c757d', fontSize: '.85rem' }}>ID: {id}</p>

      {/* Reconstrucción de estado en fecha */}
      <div className="card" style={{ marginTop: '1.5rem' }}>
        <h4>Reconstruir estado en una fecha</h4>
        <form onSubmit={buscarEstado} style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label>Fecha</label>
            <input type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} required />
          </div>
          <button className="btn btn-primary" type="submit" disabled={loading}>
            {loading ? 'Reconstruyendo...' : 'Ver estado'}
          </button>
        </form>
        {error && <div className="alert alert-error" style={{ marginTop: '1rem' }}>{error}</div>}
        {estado && (
          <div style={{ marginTop: '1rem', background: '#f8f9fa', padding: '1rem', borderRadius: 4 }}>
            <h5>Estado al {fecha}</h5>
            <table style={{ borderCollapse: 'collapse', width: '100%', marginTop: '.5rem', fontSize: '.85rem' }}>
              <tbody>
                {Object.entries(estado).filter(([k]) => !k.startsWith('_')).map(([k, v]) => (
                  <tr key={k} style={{ borderBottom: '1px solid #dee2e6' }}>
                    <td style={{ padding: '.3rem .5rem', fontWeight: 600, color: '#6c757d', width: '35%' }}>{k}</td>
                    <td style={{ padding: '.3rem .5rem' }}>
                      {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Línea de tiempo de eventos */}
      <div style={{ marginTop: '2rem' }}>
        <h4>Línea de tiempo de eventos ({historial.length})</h4>
        {historial.length === 0 ? (
          <p style={{ color: '#6c757d' }}>Sin eventos registrados.</p>
        ) : (
          <div style={{ position: 'relative', paddingLeft: '2rem' }}>
            {/* Línea vertical */}
            <div style={{ position: 'absolute', left: '0.5rem', top: 0, bottom: 0, width: 2, background: '#dee2e6' }} />
            {historial.map((e) => (
              <div key={e._id} style={{ position: 'relative', marginBottom: '1.2rem' }}>
                {/* Dot */}
                <div style={{
                  position: 'absolute', left: '-1.75rem', top: '.2rem',
                  width: 12, height: 12, borderRadius: '50%',
                  background: TIPO_COLOR[e.tipo_evento] || '#6c757d',
                  border: '2px solid #fff', boxShadow: '0 0 0 2px #dee2e6'
                }} />
                <div className="card" style={{ margin: 0, padding: '.7rem 1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap' }}>
                    <span style={{
                      fontSize: '.8rem', fontWeight: 700,
                      color: TIPO_COLOR[e.tipo_evento] || '#333',
                      background: '#f8f9fa', padding: '2px 8px', borderRadius: 12
                    }}>
                      v{e.version} — {e.tipo_evento}
                    </span>
                    <span style={{ fontSize: '.8rem', color: '#6c757d' }}>
                      {new Date(e.timestamp).toLocaleString()}
                    </span>
                  </div>
                  {Object.keys(e.datos_nuevos || {}).length > 0 && (
                    <p style={{ fontSize: '.8rem', marginTop: '.4rem', color: '#495057' }}>
                      {Object.entries(e.datos_nuevos).map(([k, v]) =>
                        `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`
                      ).join(' | ')}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
