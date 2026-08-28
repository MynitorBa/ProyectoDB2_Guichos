import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import HomePage from './pages/HomePage'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import CatalogPage from './pages/CatalogPage'
import ProductDetailPage from './pages/ProductDetailPage'
import CartPage from './pages/CartPage'
import CheckoutPage from './pages/CheckoutPage'
import OrdersPage from './pages/OrdersPage'
import OrderDetailPage from './pages/OrderDetailPage'
import AdminPage from './pages/AdminPage'
import ProductHistoryPage from './pages/ProductHistoryPage'
import ProfilePage from './pages/ProfilePage'
import VendorPage from './pages/VendorPage'

// Guarda de ruta: redirige al login si no hay sesión, o a "/" si el usuario no tiene el rol requerido
function PrivateRoute({ children, roles }) {
  const { user, loading } = useAuth()
  if (loading) return <p>Cargando...</p>
  if (!user) return <Navigate to="/login" />
  if (roles && !roles.some((r) => user.roles?.includes(r))) return <Navigate to="/" />
  return children
}

export default function Router() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/catalog" element={<CatalogPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/products/:id" element={<ProductDetailPage />} />
      <Route path="/cart" element={<PrivateRoute><CartPage /></PrivateRoute>} />
      <Route path="/checkout" element={<PrivateRoute><CheckoutPage /></PrivateRoute>} />
      <Route path="/orders" element={<PrivateRoute><OrdersPage /></PrivateRoute>} />
      <Route path="/orders/:id" element={<PrivateRoute><OrderDetailPage /></PrivateRoute>} />
      <Route path="/profile" element={<PrivateRoute><ProfilePage /></PrivateRoute>} />
      <Route
        path="/vendor"
        element={<PrivateRoute roles={['vendedor', 'administrador']}><VendorPage /></PrivateRoute>}
      />
      <Route
        path="/admin"
        element={<PrivateRoute roles={['administrador']}><AdminPage /></PrivateRoute>}
      />
      <Route
        path="/admin/products/:id/history"
        element={<PrivateRoute roles={['administrador']}><ProductHistoryPage /></PrivateRoute>}
      />
    </Routes>
  )
}
