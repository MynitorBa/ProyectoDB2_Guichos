import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getOrder } from '../api/orders'

export default function OrderDetailPage() {
  const { id } = useParams()
  const [pedido, setPedido] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    getOrder(id).then((r) => setPedido(r.data))
  }, [id])

  if (!pedido) return <p style={{ margin: '2rem' }}>Cargando...</p>

  return (
    <div style={{ maxWidth: 700, margin: '2rem auto' }}>
      <button className="btn btn-secondary" onClick={() => navigate('/orders')} style={{ marginBottom: '1rem' }}>
        ← Mis pedidos
      </button>
      <div className="card">
        <h2>Pedido #{pedido.id}</h2>
        <p>Estado: <strong>{pedido.estado}</strong></p>
        <p>Fecha: {new Date(pedido.fecha).toLocaleString()}</p>
        <hr style={{ margin: '1rem 0' }} />
        <h4>Productos</h4>
        {pedido.lineas?.map((l, i) => (
          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '.4rem 0', borderBottom: '1px solid #dee2e6' }}>
            <div>
              <strong>{l.producto_nombre}</strong>
              <p style={{ fontSize: '.85rem', color: '#6c757d' }}>GTQ {l.precio_unitario} × {l.cantidad}</p>
            </div>
            <span>GTQ {l.subtotal?.toFixed(2)}</span>
          </div>
        ))}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '.5rem' }}>
          <span>Subtotal</span><span>GTQ {pedido.subtotal}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>IVA (12%)</span><span>GTQ {pedido.impuestos}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 700, fontSize: '1.1rem', marginTop: '.5rem' }}>
          <span>Total</span><span>GTQ {pedido.total}</span>
        </div>
        {pedido.pagos?.length > 0 && (
          <>
            <hr style={{ margin: '1rem 0' }} />
            <h4>Pago</h4>
            {pedido.pagos.map((p, i) => (
              <p key={i} style={{ fontSize: '.85rem' }}>
                {p.estado} — Ref: {p.referencia} — GTQ {p.monto}
              </p>
            ))}
          </>
        )}
      </div>
    </div>
  )
}
