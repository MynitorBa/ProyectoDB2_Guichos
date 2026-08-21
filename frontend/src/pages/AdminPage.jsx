import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCatalogStats, createProduct, getCategories, getCategorySchema } from '../api/products'

export default function AdminPage() {
  const [stats, setStats] = useState(null)
  const [categorias, setCategorias] = useState([])
  const [esquema, setEsquema] = useState(null)
  const [form, setForm] = useState({ sku: '', nombre: '', descripcion: '', precio: '', categoria_slug: '' })
  const [atributos, setAtributos] = useState({})
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    getCatalogStats().then((r) => setStats(r.data[0]))
    getCategories().then((r) => setCategorias(r.data))
  }, [])

  const onCategoriaChange = async (slug) => {
    setForm((f) => ({ ...f, categoria_slug: slug }))
    setAtributos({})
    if (slug) {
      try {
        const { data } = await getCategorySchema(slug)
        setEsquema(data)
      } catch { setEsquema(null) }
    } else {
      setEsquema(null)
    }
  }

  const handleCreate = async (e) => {
    e.preventDefault()
    setError('')
    setMsg('')
    try {
      await createProduct({ ...form, precio: parseFloat(form.precio), atributos })
      setMsg('Producto creado exitosamente.')
      setForm({ sku: '', nombre: '', descripcion: '', precio: '', categoria_slug: '' })
      setAtributos({})
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al crear producto.')
    }
  }

  return (
    <div style={{ maxWidth: 1000, margin: '2rem auto' }}>
      <h2>Panel de administración</h2>

      {/* Estadísticas del catálogo (aggregation) */}
      {stats && (
        <div className="card" style={{ marginTop: '1rem' }}>
          <h3>Estadísticas del catálogo (MongoDB aggregation)</h3>
          <p>Total productos activos: {stats.resumen_global?.[0]?.total_productos}</p>
          <p>Disponibles: {stats.resumen_global?.[0]?.total_disponibles}</p>
          <p>Precio promedio: GTQ {stats.resumen_global?.[0]?.precio_promedio_global?.toFixed(2)}</p>
          <h4 style={{ marginTop: '1rem' }}>Por categoría</h4>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '.85rem' }}>
            <thead>
              <tr style={{ background: '#e9ecef' }}>
                {['Categoría', 'Total', 'Disponibles', 'Precio mín', 'Precio máx', 'Promedio'].map((h) => (
                  <th key={h} style={{ padding: '.4rem', textAlign: 'left', borderBottom: '2px solid #dee2e6' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {stats.estadisticas_por_categoria?.map((c) => (
                <tr key={c.slug} style={{ borderBottom: '1px solid #dee2e6' }}>
                  <td style={{ padding: '.4rem' }}>{c.categoria_nombre}</td>
                  <td style={{ padding: '.4rem' }}>{c.total_productos}</td>
                  <td style={{ padding: '.4rem' }}>{c.disponibles}</td>
                  <td style={{ padding: '.4rem' }}>GTQ {c.precio_minimo?.toFixed(2)}</td>
                  <td style={{ padding: '.4rem' }}>GTQ {c.precio_maximo?.toFixed(2)}</td>
                  <td style={{ padding: '.4rem' }}>GTQ {c.precio_promedio?.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Formulario de creación de producto con campos dinámicos */}
      <div className="card" style={{ marginTop: '2rem' }}>
        <h3>Crear producto</h3>
        {msg && <div className="alert alert-success">{msg}</div>}
        {error && <div className="alert alert-error">{error}</div>}
        <form onSubmit={handleCreate}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            {[['sku', 'SKU'], ['nombre', 'Nombre'], ['precio', 'Precio (GTQ)']].map(([k, lbl]) => (
              <div className="form-group" key={k}>
                <label>{lbl}</label>
                <input
                  type={k === 'precio' ? 'number' : 'text'}
                  value={form[k]}
                  onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))}
                  required
                />
              </div>
            ))}
            <div className="form-group">
              <label>Categoría</label>
              <select value={form.categoria_slug} onChange={(e) => onCategoriaChange(e.target.value)} required>
                <option value="">Selecciona</option>
                {categorias.map((c) => <option key={c.slug} value={c.slug}>{c.nombre}</option>)}
              </select>
            </div>
          </div>
          <div className="form-group">
            <label>Descripción</label>
            <textarea value={form.descripcion} onChange={(e) => setForm((f) => ({ ...f, descripcion: e.target.value }))} rows={3} style={{ width: '100%' }} />
          </div>

          {/* Campos de atributos dinámicos según la categoría — esta es la parte que demuestra el esquema variable */}
          {esquema?.atributos?.length > 0 && (
            <div>
              <h4>Atributos específicos de {esquema.categoria_nombre}</h4>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                {esquema.atributos.map((attr) => (
                  <div className="form-group" key={attr.nombre}>
                    <label>{attr.etiqueta}{attr.requerido && ' *'}</label>
                    {attr.tipo === 'boolean' ? (
                      <select value={atributos[attr.nombre] || ''} onChange={(e) => setAtributos((a) => ({ ...a, [attr.nombre]: e.target.value === 'true' }))}>
                        <option value="">—</option>
                        <option value="true">Sí</option>
                        <option value="false">No</option>
                      </select>
                    ) : (
                      <input
                        type={attr.tipo === 'number' ? 'number' : 'text'}
                        placeholder={attr.placeholder}
                        value={atributos[attr.nombre] || ''}
                        onChange={(e) => setAtributos((a) => ({
                          ...a,
                          [attr.nombre]: attr.tipo === 'number' ? parseFloat(e.target.value) : e.target.value
                        }))}
                      />
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <button className="btn btn-primary" type="submit">Crear producto</button>
        </form>
      </div>
    </div>
  )
}
