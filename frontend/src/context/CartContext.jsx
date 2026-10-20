import { createContext, useContext, useState, useCallback } from 'react'
import { toast } from 'sonner'
import { getCart, addItem, removeItem, updateCantidad } from '../api/cart'
import { mensajeError } from '../lib/errors'

const CartContext = createContext(null)

// Contexto global del carrito: expone cart, loading, error, fetchCart, add, remove y update.
export function CartProvider({ children }) {
  const [cart, setCart] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(false)
  // Mensaje cuando el carrito no se pudo consultar (por ejemplo, Redis caído).
  const [error, setError] = useState(null)
  // Evita mostrar «carrito vacío» antes de que llegue la primera respuesta.
  const [cargado, setCargado] = useState(false)

  // fetchCart está memoizado para usarse como dependencia en useEffect sin bucles infinitos
  const fetchCart = useCallback(async () => {
    try {
      const r = await getCart()
      setCart(r.data)
      setError(null)
    } catch (err) {
      // Sin sesión no hay carrito que mostrar; cualquier otra falla sí se informa.
      if (err?.response?.status === 401 || err?.response?.status === 403) {
        setError(null)
        return
      }
      setError(mensajeError(err, 'No se pudo cargar el carrito.'))
    } finally {
      setCargado(true)
    }
  }, [])

  // Quien agrega muestra su propio mensaje (flash, stock, etc.), por eso el error se propaga.
  const add = async (oferta_id, cantidad = 1) => {
    setLoading(true)
    try {
      await addItem(oferta_id, cantidad)
      await fetchCart()
    } finally {
      setLoading(false)
    }
  }

  const remove = async (item_id) => {
    setLoading(true)
    try {
      await removeItem(item_id)
      await fetchCart()
      return true
    } catch (err) {
      toast.error(mensajeError(err, 'No se pudo quitar el producto del carrito.'))
      return false
    } finally {
      setLoading(false)
    }
  }

  const update = async (oferta_id, cantidad) => {
    setLoading(true)
    try {
      await updateCantidad(oferta_id, cantidad)
      await fetchCart()
      return true
    } catch (err) {
      toast.error(mensajeError(err, 'No se pudo actualizar la cantidad.'))
      return false
    } finally {
      setLoading(false)
    }
  }

  return (
    <CartContext.Provider value={{ cart, loading, error, cargado, fetchCart, add, remove, update }}>
      {children}
    </CartContext.Provider>
  )
}

export const useCart = () => useContext(CartContext)
