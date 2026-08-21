import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getOrders } from '../api/orders'

const ESTADO_COLOR = {
  pendiente: '#856404', confirmado: '#0f5132', enviado: '#084298',
  entregado: '#0f5132', cancelado: '#842029', reembolsado: '#6c757d',
}

export default function OrdersPage() {
  const [pedidos, setPedidos] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getOrders().then((r) => setPedidos(r.data)).finally(() => setLoading(false))
  }, [])

  if (loading) return <p style={{ margin: '2rem' }}>Cargando pedidos...</p>

  return (
    <div style={{ maxWidth: 700, margin: '2rem auto' }}>
      <h2>Mis pedidos</h2>
      {pedidos.length === 0 ? (
        <p style={{ margin: '2rem 0' }}>No tienes pedidos. <Link to="/">Ir al catálogo</Link></p>
      ) : (
        pedidos.map((p) => (
          <div key={p.id} className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <strong>Pedido #{p.id}</strong>
              <p style={{ fontSize: '.85rem', color: '#6c757d' }}>{new Date(p.fecha).toLocaleDateString()}</p>
              <span style={{ fontSize: '.8rem', padding: '2px 8px', borderRadius: 12, background: '#e9ecef', color: ESTADO_COLOR[p.estado] || '#333' }}>
                {p.estado}
              </span>
            </div>
            <div style={{ textAlign: 'right' }}>
              <p style={{ fontWeight: 700 }}>GTQ {p.total?.toFixed(2)}</p>
              <Link to={`/orders/${p.id}`} style={{ fontSize: '.85rem' }}>Ver detalle</Link>
            </div>
          </div>
        ))
      )}
    </div>
  )
}
