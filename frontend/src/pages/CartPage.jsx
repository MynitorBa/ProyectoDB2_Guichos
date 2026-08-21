import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useCart } from '../context/CartContext'

export default function CartPage() {
  const { cart, loading, fetchCart, remove } = useCart()

  useEffect(() => { fetchCart() }, [fetchCart])

  return (
    <div style={{ maxWidth: 700, margin: '2rem auto' }}>
      <h2>Mi carrito</h2>
      {loading && <p>Actualizando...</p>}
      {cart.items.length === 0 ? (
        <p style={{ margin: '2rem 0' }}>El carrito está vacío. <Link to="/">Ver catálogo</Link></p>
      ) : (
        <>
          {cart.items.map((item) => (
            <div key={item.id} className="card" style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <div style={{ flex: 1 }}>
                <strong>{item.nombre}</strong>
                <p style={{ fontSize: '.85rem', color: '#6c757d' }}>
                  GTQ {item.precio?.toFixed(2)} × {item.cantidad} = GTQ {item.subtotal?.toFixed(2)}
                </p>
              </div>
              <button className="btn btn-danger" onClick={() => remove(item.id)}>Quitar</button>
            </div>
          ))}
          <div className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <strong style={{ fontSize: '1.1rem' }}>Total: GTQ {cart.total?.toFixed(2)}</strong>
            <Link to="/checkout" className="btn btn-primary">Proceder al pago</Link>
          </div>
        </>
      )}
    </div>
  )
}
