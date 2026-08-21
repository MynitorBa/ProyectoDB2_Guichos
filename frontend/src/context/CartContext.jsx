import { createContext, useContext, useState, useCallback } from 'react'
import { getCart, addItem, removeItem } from '../api/cart'

const CartContext = createContext(null)

export function CartProvider({ children }) {
  const [cart, setCart] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(false)

  const fetchCart = useCallback(async () => {
    try {
      const r = await getCart()
      setCart(r.data)
    } catch {
      /* no autenticado */
    }
  }, [])

  const add = async (producto_id, cantidad = 1) => {
    setLoading(true)
    await addItem(producto_id, cantidad)
    await fetchCart()
    setLoading(false)
  }

  const remove = async (item_id) => {
    setLoading(true)
    await removeItem(item_id)
    await fetchCart()
    setLoading(false)
  }

  return (
    <CartContext.Provider value={{ cart, loading, fetchCart, add, remove }}>
      {children}
    </CartContext.Provider>
  )
}

export const useCart = () => useContext(CartContext)
