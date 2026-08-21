import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getProduct } from '../api/products'
import { useCart } from '../context/CartContext'

export default function ProductDetailPage() {
  const { id } = useParams()
  const [producto, setProducto] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const { add } = useCart()
  const navigate = useNavigate()

  useEffect(() => {
    getProduct(id)
      .then((r) => setProducto(r.data))
      .catch(() => setError('Producto no encontrado.'))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return <p style={{ margin: '2rem' }}>Cargando...</p>
  if (error) return <div className="alert alert-error" style={{ margin: '2rem' }}>{error}</div>
  if (!producto) return null

  return (
    <div style={{ maxWidth: 900, margin: '2rem auto' }}>
      <button className="btn btn-secondary" onClick={() => navigate(-1)} style={{ marginBottom: '1rem' }}>
        ← Volver
      </button>
      <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
        {/* Imagen */}
        <div style={{ flex: '0 0 320px' }}>
          {producto.imagenes?.[0]?.url ? (
            <img src={producto.imagenes[0].url} alt={producto.nombre} style={{ width: '100%', borderRadius: 8 }} />
          ) : (
            <div style={{ height: 280, background: '#e9ecef', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#adb5bd' }}>
              Sin imagen
            </div>
          )}
        </div>

        {/* Datos */}
        <div style={{ flex: 1 }}>
          <p style={{ color: '#6c757d', fontSize: '.85rem' }}>{producto.categoria?.nombre}</p>
          <h2 style={{ margin: '.3rem 0' }}>{producto.nombre}</h2>
          <p style={{ fontSize: '1.5rem', fontWeight: 700, color: '#0d6efd' }}>
            GTQ {producto.precio?.toFixed(2)}
          </p>
          <p style={{ margin: '1rem 0', color: '#495057' }}>{producto.descripcion}</p>

          {/* Vendedor */}
          {producto.vendedor_nombre && (
            <p style={{ fontSize: '.85rem' }}>Vendedor: <strong>{producto.vendedor_nombre}</strong></p>
          )}

          {/* Resumen de reseñas */}
          {producto.resumen_resenas && (
            <p style={{ fontSize: '.85rem', margin: '.5rem 0' }}>
              ⭐ {producto.resumen_resenas.promedio?.toFixed(1) || '0.0'} ({producto.resumen_resenas.total} reseñas)
            </p>
          )}

          {/* Atributos variables — renderizados dinámicamente según la categoría */}
          {producto.atributos && Object.keys(producto.atributos).length > 0 && (
            <div style={{ marginTop: '1rem' }}>
              <h4>Especificaciones</h4>
              <table style={{ borderCollapse: 'collapse', width: '100%', marginTop: '.5rem' }}>
                <tbody>
                  {Object.entries(producto.atributos).map(([k, v]) => (
                    <tr key={k} style={{ borderBottom: '1px solid #dee2e6' }}>
                      <td style={{ padding: '.3rem .5rem', fontWeight: 600, fontSize: '.85rem', color: '#6c757d', width: '40%' }}>
                        {k.replace(/_/g, ' ')}
                      </td>
                      <td style={{ padding: '.3rem .5rem', fontSize: '.85rem' }}>
                        {typeof v === 'boolean' ? (v ? 'Sí' : 'No') : String(v)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {producto.disponible ? (
            <button
              className="btn btn-primary"
              style={{ marginTop: '1.5rem', padding: '.6rem 1.5rem' }}
              onClick={() => add(producto.mysql_id, 1)}
            >
              Agregar al carrito
            </button>
          ) : (
            <p style={{ color: '#dc3545', marginTop: '1rem', fontWeight: 600 }}>Sin stock</p>
          )}
        </div>
      </div>
    </div>
  )
}
