import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getCart } from '../api/cart'
import { checkout, getAddresses } from '../api/orders'

export default function CheckoutPage() {
  const [cart, setCart] = useState({ items: [], total: 0 })
  const [addresses, setAddresses] = useState([])
  const [dirId, setDirId] = useState('')
  const [metodoPago, setMetodoPago] = useState('1')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    getCart().then((r) => setCart(r.data))
    getAddresses().then((r) => {
      setAddresses(r.data)
      const def = r.data.find((d) => d.es_predeterminada)
      if (def) setDirId(String(def.id))
    })
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const items = cart.items.map((i) => ({ producto_id: i.producto_id, cantidad: i.cantidad }))
      const { data } = await checkout({ direccion_id: Number(dirId), metodo_pago_id: Number(metodoPago), items })
      navigate(`/orders/${data.pedido_id}`)
    } catch (err) {
      const detail = err.response?.data?.detail
      setError(typeof detail === 'object' ? detail.detail : (detail || 'Error al procesar el pedido.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: 600, margin: '2rem auto' }}>
      <h2>Checkout</h2>
      {error && <div className="alert alert-error">{error}</div>}
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>Dirección de envío</label>
          <select value={dirId} onChange={(e) => setDirId(e.target.value)} required>
            <option value="">Selecciona una dirección</option>
            {addresses.map((d) => (
              <option key={d.id} value={d.id}>
                {d.linea1}, {d.municipio}, {d.departamento}
              </option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label>Método de pago</label>
          <select value={metodoPago} onChange={(e) => setMetodoPago(e.target.value)}>
            <option value="1">Tarjeta de crédito</option>
            <option value="2">Tarjeta de débito</option>
            <option value="3">Transferencia bancaria</option>
            <option value="4">Pago contra entrega</option>
          </select>
        </div>

        <div className="card">
          <h4>Resumen del pedido</h4>
          {cart.items.map((i) => (
            <div key={i.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '.3rem 0' }}>
              <span>{i.nombre} × {i.cantidad}</span>
              <span>GTQ {i.subtotal?.toFixed(2)}</span>
            </div>
          ))}
          <hr style={{ margin: '.5rem 0' }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 700 }}>
            <span>Total (inc. 12% IVA)</span>
            <span>GTQ {(cart.total * 1.12).toFixed(2)}</span>
          </div>
        </div>

        <button className="btn btn-primary" type="submit" disabled={loading || cart.items.length === 0} style={{ width: '100%', marginTop: '1rem' }}>
          {loading ? 'Procesando...' : 'Confirmar pedido'}
        </button>
      </form>
    </div>
  )
}
