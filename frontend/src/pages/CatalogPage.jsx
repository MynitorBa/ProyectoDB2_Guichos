import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getProducts, getCategories, getCategorySchema } from '../api/products'
import { useCart } from '../context/CartContext'

export default function CatalogPage() {
  const [productos, setProductos] = useState([])
  const [categorias, setCategorias] = useState([])
  const [esquema, setEsquema] = useState(null)
  const [filtros, setFiltros] = useState({ categoria: '', precio_min: '', precio_max: '', orden: 'precio_asc' })
  const [attrFiltros, setAttrFiltros] = useState({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const { add } = useCart()

  useEffect(() => {
    getCategories().then((r) => setCategorias(r.data))
  }, [])

  useEffect(() => {
    if (filtros.categoria) {
      getCategorySchema(filtros.categoria)
        .then((r) => setEsquema(r.data))
        .catch(() => setEsquema(null))
    } else {
      setEsquema(null)
      setAttrFiltros({})
    }
  }, [filtros.categoria])

  useEffect(() => {
    const params = {}
    if (filtros.categoria) params.categoria = filtros.categoria
    if (filtros.precio_min) params.precio_min = filtros.precio_min
    if (filtros.precio_max) params.precio_max = filtros.precio_max
    params.orden = filtros.orden

    setLoading(true)
    getProducts(params)
      .then((r) => setProductos(r.data.items || []))
      .catch(() => setError('Error al cargar productos.'))
      .finally(() => setLoading(false))
  }, [filtros])

  const setF = (k) => (e) => setFiltros((f) => ({ ...f, [k]: e.target.value }))

  return (
    <div>
      <h2 style={{ margin: '1rem 0' }}>Catálogo de productos</h2>
      <div style={{ display: 'flex', gap: '1.5rem' }}>
        {/* Sidebar de filtros */}
        <aside style={{ width: 220, flexShrink: 0 }}>
          <div className="card">
            <h4>Categoría</h4>
            <select value={filtros.categoria} onChange={setF('categoria')} style={{ width: '100%', marginBottom: '.5rem' }}>
              <option value="">Todas</option>
              {categorias.map((c) => (
                <option key={c.slug} value={c.slug}>{c.nombre}</option>
              ))}
            </select>

            {/* Filtros dinámicos por atributos de la categoría */}
            {esquema?.atributos?.length > 0 && (
              <div style={{ marginTop: '.5rem' }}>
                <h4>Atributos</h4>
                {esquema.atributos.map((attr) => (
                  <div key={attr.nombre} style={{ marginBottom: '.4rem' }}>
                    <label style={{ fontSize: '.85rem' }}>{attr.etiqueta}</label>
                    <input
                      type={attr.tipo === 'number' ? 'number' : 'text'}
                      placeholder={attr.placeholder}
                      value={attrFiltros[attr.nombre] || ''}
                      onChange={(e) => setAttrFiltros((f) => ({ ...f, [attr.nombre]: e.target.value }))}
                      style={{ width: '100%', padding: '.3rem', fontSize: '.85rem' }}
                    />
                  </div>
                ))}
              </div>
            )}

            <h4 style={{ marginTop: '.7rem' }}>Precio (GTQ)</h4>
            <input type="number" placeholder="Mín" value={filtros.precio_min} onChange={setF('precio_min')} style={{ width: '100%', marginBottom: '.3rem' }} />
            <input type="number" placeholder="Máx" value={filtros.precio_max} onChange={setF('precio_max')} style={{ width: '100%', marginBottom: '.5rem' }} />

            <h4>Ordenar por</h4>
            <select value={filtros.orden} onChange={setF('orden')} style={{ width: '100%' }}>
              <option value="precio_asc">Precio: menor a mayor</option>
              <option value="precio_desc">Precio: mayor a menor</option>
              <option value="nombre_asc">Nombre A-Z</option>
              <option value="reciente">Más recientes</option>
            </select>
          </div>
        </aside>

        {/* Grid de productos */}
        <div style={{ flex: 1 }}>
          {error && <div className="alert alert-error">{error}</div>}
          {loading ? (
            <p>Cargando productos...</p>
          ) : productos.length === 0 ? (
            <p>No se encontraron productos con esos filtros.</p>
          ) : (
            <div className="grid">
              {productos.map((p) => (
                <div key={p._id} className="card product-card">
                  {p.imagenes?.[0]?.url ? (
                    <img src={p.imagenes[0].url} alt={p.nombre} />
                  ) : (
                    <div style={{ height: 180, background: '#e9ecef', borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#adb5bd' }}>
                      Sin imagen
                    </div>
                  )}
                  <h3><Link to={`/products/${p._id}`}>{p.nombre}</Link></h3>
                  <p className="price">GTQ {p.precio?.toFixed(2)}</p>
                  <p style={{ fontSize: '.8rem', color: '#6c757d' }}>{p.categoria?.nombre}</p>
                  <button
                    className="btn btn-primary"
                    style={{ width: '100%', marginTop: '.5rem', fontSize: '.85rem' }}
                    onClick={() => add(p.mysql_id, 1)}
                  >
                    Agregar al carrito
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
