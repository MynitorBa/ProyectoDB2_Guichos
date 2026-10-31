import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  CheckCircle, MapPin, CreditCard, ClipboardList, ChevronRight, Landmark, ArrowLeftRight, Package,
  AlertTriangle, Clock, RotateCw, XCircle,
} from 'lucide-react'
import { toast } from 'sonner'
import { getCart } from '../api/cart'
import { checkout, getAddresses } from '../api/orders'
import { useCart } from '../context/CartContext'
import { Button } from '../components/ui/button'
import { Separator } from '../components/ui/separator'
import { Badge } from '../components/ui/badge'
import { cn, formatQ } from '../lib/utils'

const IVA_RATE = 0.12

const PAYMENT_METHODS = [
  { id: 1, label: 'Tarjeta de crédito',    Icon: CreditCard      },
  { id: 2, label: 'Tarjeta de débito',     Icon: Landmark        },
  { id: 3, label: 'Transferencia bancaria', Icon: ArrowLeftRight  },
  { id: 4, label: 'Contra entrega',         Icon: Package         },
]

// ── Intento de compra idempotente ─────────────────────────────────────────────
// Cada intento lleva una clave única. Se conserva (también al recargar la
// página) mientras el intento sea el mismo y se reutiliza al reintentar tras un
// error de red: el servidor devuelve el pedido ya creado en lugar de crear otro.
const CLAVE_INTENTO = 'tiendaya.checkout.intento'

function claveDelIntento(firma) {
  try {
    const guardado = JSON.parse(sessionStorage.getItem(CLAVE_INTENTO) || 'null')
    if (guardado?.firma === firma) return guardado.clave
  } catch {
    // sessionStorage no disponible: cada intento usa una clave nueva.
  }
  const clave = crypto.randomUUID()
  try {
    sessionStorage.setItem(CLAVE_INTENTO, JSON.stringify({ firma, clave }))
  } catch {
    // Sin almacenamiento la clave vive solo durante este intento.
  }
  return clave
}

function descartarIntento() {
  try { sessionStorage.removeItem(CLAVE_INTENTO) } catch { /* nada que limpiar */ }
}

const TIPO_ERROR = {
  PRICE_CHANGED: 'precio',
  PAYMENT_DECLINED: 'rechazado',
  PAYMENT_UNAVAILABLE: 'no_disponible',
  ORDER_NOT_FULFILLABLE: 'no_cumplible',
  PAYMENT_PENDING_EXISTS: 'pendiente_existente',
  CHECKOUT_IN_PROGRESS: 'en_proceso',
}

const AVISOS = {
  rechazado:           { titulo: 'Pago rechazado', tono: 'error', Icon: XCircle },
  no_disponible:       { titulo: 'Pasarela de pagos no disponible', tono: 'error', Icon: XCircle },
  no_cumplible:        { titulo: 'Pedido no disponible', tono: 'error', Icon: XCircle },
  pendiente_existente: { titulo: 'Tienes un pago en verificación', tono: 'aviso', Icon: Clock },
  en_proceso:          { titulo: 'Tu compra se está procesando', tono: 'aviso', Icon: Clock },
  red:                 { titulo: 'Sin respuesta del servidor', tono: 'aviso', Icon: AlertTriangle },
  precio:              { titulo: 'Los precios cambiaron', tono: 'aviso', Icon: AlertTriangle },
  generico:            { titulo: 'No se pudo completar la compra', tono: 'error', Icon: XCircle },
}

function AvisoCheckout({ error, reintentando, onReintentar }) {
  const aviso = AVISOS[error.tipo] || AVISOS.generico
  const { Icon } = aviso
  const colores = aviso.tono === 'error'
    ? 'bg-[var(--color-error)]/10 border-[var(--color-error)]/30 text-[var(--color-error)]'
    : 'bg-amber-50 border-amber-300 text-amber-900'
  const reintentoSeguro = error.tipo === 'red' || error.tipo === 'en_proceso'
  return (
    <div role="alert" className={cn('rounded-[var(--radius-md)] border px-4 py-3 space-y-2', colores)}>
      <p className="flex items-center gap-2 font-sans text-sm font-semibold">
        <Icon size={16} className="shrink-0" /> {aviso.titulo}
      </p>
      <p className="font-sans text-sm text-[var(--color-text-secondary)]">{error.mensaje}</p>
      <div className="flex flex-wrap gap-2 pt-1">
        {reintentoSeguro && (
          <Button size="sm" variant="secondary" loading={reintentando} onClick={onReintentar}>
            <RotateCw size={13} /> Reintentar de forma segura
          </Button>
        )}
        {error.pedidoId && (
          <Button size="sm" variant="ghost" asChild>
            <Link to={`/orders/${error.pedidoId}`}>Ver pedido #{error.pedidoId}</Link>
          </Button>
        )}
      </div>
    </div>
  )
}

const STEPS = [
  { id: 1, label: 'Dirección', icon: MapPin },
  { id: 2, label: 'Pago', icon: CreditCard },
  { id: 3, label: 'Confirmación', icon: ClipboardList },
]

// Barra de progreso visual de los 3 pasos del checkout: Dirección → Pago → Confirmación
function StepIndicator({ current }) {
  return (
    <div className="flex items-center justify-center gap-0 mb-8">
      {STEPS.map((step, idx) => {
        const done = current > step.id
        const active = current === step.id
        const Icon = step.icon
        return (
          <div key={step.id} className="flex items-center">
            <div className="flex flex-col items-center gap-1">
              <div
                className={cn(
                  'h-9 w-9 rounded-full flex items-center justify-center border-2 transition-colors',
                  done
                    ? 'bg-[var(--color-success)] border-[var(--color-success)] text-white'
                    : active
                    ? 'bg-[var(--color-action)] border-[var(--color-action)] text-white'
                    : 'bg-[var(--color-surface)] border-[var(--color-border)] text-[var(--color-text-muted)]'
                )}
              >
                {done ? <CheckCircle size={16} /> : <Icon size={16} />}
              </div>
              <span
                className={cn(
                  'text-xs font-sans font-medium',
                  active
                    ? 'text-[var(--color-action)]'
                    : done
                    ? 'text-[var(--color-success)]'
                    : 'text-[var(--color-text-muted)]'
                )}
              >
                {step.label}
              </span>
            </div>
            {idx < STEPS.length - 1 && (
              <div
                className={cn(
                  'h-0.5 w-16 sm:w-24 mx-2 mb-4 transition-colors',
                  current > step.id ? 'bg-[var(--color-success)]' : 'bg-[var(--color-border)]'
                )}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

function OrderSummary({ items, cart }) {
  const total = items.reduce(
    (acc, item) => acc + (item.subtotal ?? item.precio * item.cantidad),
    0
  )
  const subtotal = total / (1 + IVA_RATE)
  const iva = total - subtotal

  return (
    <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5 sticky top-20">
      <h3 className="font-display font-semibold text-base text-[var(--color-text-primary)] mb-4">
        Resumen del pedido
      </h3>
      <div className="space-y-2 mb-4">
        {items.map((item) => (
          <div key={item.oferta_id} className="flex justify-between gap-2 text-sm font-sans">
            <span className="text-[var(--color-text-secondary)] line-clamp-1 flex-1">
              {item.nombre} <span className="text-[var(--color-text-muted)]">×{item.cantidad}</span>
            </span>
            <span className="font-mono text-[var(--color-text-primary)] shrink-0">
              {formatQ(item.subtotal ?? item.precio * item.cantidad)}
            </span>
          </div>
        ))}
      </div>
      <Separator />
      <div className="space-y-2 mt-3">
        <div className="flex justify-between font-sans text-sm text-[var(--color-text-secondary)]">
          <span>Subtotal</span>
          <span className="font-mono">{formatQ(subtotal)}</span>
        </div>
        <div className="flex justify-between font-sans text-sm text-[var(--color-text-secondary)]">
          <span>IVA (12%)</span>
          <span className="font-mono">{formatQ(iva)}</span>
        </div>
        <Separator />
        <div className="flex justify-between font-display font-bold text-base text-[var(--color-text-primary)]">
          <span>Total</span>
          <span className="font-mono">{formatQ(total)}</span>
        </div>
      </div>
    </div>
  )
}

// Proceso de compra en 3 pasos: selección de dirección, método de pago y confirmación final que llama a /orders/checkout
export default function CheckoutPage() {
  const { fetchCart } = useCart()
  const [cart, setCart] = useState({ items: [], total: 0 })
  const [addresses, setAddresses] = useState([])
  const [step, setStep] = useState(1)
  const [selectedAddress, setSelectedAddress] = useState(null)
  const [selectedPayment, setSelectedPayment] = useState(1)
  const [submitting, setSubmitting] = useState(false)
  const [successData, setSuccessData] = useState(null)
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    getCart().then((r) => setCart(r.data))
    getAddresses()
      .then((r) => {
        const addrs = r.data || []
        setAddresses(addrs)
        const def = addrs.find((d) => d.es_predeterminada)
        if (def) setSelectedAddress(def.id)
        else if (addrs.length > 0) setSelectedAddress(addrs[0].id)
      })
      .catch(() => {})
  }, [])

  const items = cart?.items || []
  const priceChanges = items.filter((item) => item.precio_cambio && !item.sin_stock)

  // Firma del intento: mismo carrito, dirección y método ⇒ mismo intento de compra.
  const firmaIntento = JSON.stringify({
    items: items.map((i) => [i.oferta_id, i.cantidad]).sort((a, b) => a[0] - b[0]),
    direccion: selectedAddress,
    metodo: selectedPayment,
  })

  async function handleConfirm() {
    setError(null)
    setSubmitting(true)
    const clave = claveDelIntento(firmaIntento)
    try {
      const orderItems = items.map((i) => ({
        oferta_id: i.oferta_id,
        cantidad: i.cantidad,
      }))
      const res = await checkout({
        direccion_id: Number(selectedAddress),
        metodo_pago_id: Number(selectedPayment),
        items: orderItems,
        confirmar_cambios_precio: priceChanges.length > 0,
        precios_confirmados: Object.fromEntries(
          items.map((item) => [item.oferta_id, item.precio])
        ),
      }, clave)
      descartarIntento()
      if (res.status === 202 && res.data?.codigo === 'ORDER_QUEUED') {
        // La base principal no respondía: el pedido quedó en cola sin cobrar.
        toast.info(res.data.detail, { duration: 10000 })
        navigate('/orders')
        return
      }
      if (res.status === 202) {
        // El cobro salió pero la pasarela no confirmó: se resolverá en segundo plano.
        toast.info('Estamos verificando tu pago con la pasarela.')
        navigate(`/orders/${res.data.pedido_id}`, { state: { verificando: true } })
        return
      }
      setSuccessData(res.data)
      await fetchCart()
    } catch (err) {
      if (!err?.response) {
        // Sin respuesta (red caída o timeout): no sabemos si se creó el pedido.
        // Se conserva la clave para que el reintento sea seguro.
        setError({ tipo: 'red', mensaje: 'No recibimos respuesta del servidor. Tu compra pudo haberse registrado; reintentar es seguro y no generará un cobro doble.' })
        return
      }
      const raw = err.response.data?.detail
      const code = typeof raw === 'object' ? raw?.code : err.response.data?.code
      const msg =
        typeof raw === 'string'
          ? raw
          : typeof raw?.detail === 'string'
          ? raw.detail
          : Array.isArray(raw)
          ? 'Datos de envío inválidos. Verifica tu dirección y método de pago.'
          : 'No se pudo procesar el pedido. Intenta de nuevo.'
      if (err.response.status >= 500 && !TIPO_ERROR[code]) {
        // El servidor falló sin un resultado definitivo (pudo caer después de
        // confirmar): igual que sin respuesta, se conserva la clave y reintentar
        // devuelve el pedido ya creado en lugar de crear otro o cobrar dos veces.
        setError({ tipo: 'red', mensaje: 'No pudimos confirmar el resultado de tu compra. Pudo haberse registrado; reintentar es seguro y no generará un cobro doble.' })
        return
      }
      const tipo = TIPO_ERROR[code] || 'generico'
      // La compra sigue en curso: la misma clave permite consultar su resultado.
      if (tipo !== 'en_proceso') descartarIntento()
      if (code === 'PRICE_CHANGED') {
        try {
          const refreshed = await getCart()
          setCart(refreshed.data)
        } catch {
          // El mensaje original de cambio de precio sigue siendo el relevante.
        }
      }
      if (tipo === 'rechazado' || tipo === 'no_disponible' || tipo === 'no_cumplible') {
        await fetchCart() // el carrito se conserva para reintentar con otro medio
      }
      setError({ tipo, mensaje: msg, pedidoId: err.response.data?.pedido_id ?? raw?.pedido_id })
      if (tipo === 'generico') toast.error(msg)
    } finally {
      setSubmitting(false)
    }
  }

  if (successData) {
    return (
      <div className="min-h-screen bg-[var(--color-background)] flex items-center justify-center px-4">
        <div className="max-w-md w-full text-center">
          <div className="h-20 w-20 rounded-full bg-[var(--color-success)]/15 flex items-center justify-center mx-auto mb-6">
            <CheckCircle size={40} className="text-[var(--color-success)]" />
          </div>
          <h1 className="font-display font-bold text-3xl text-[var(--color-text-primary)] mb-2">
            ¡Pedido confirmado!
          </h1>
          <p className="font-sans text-sm text-[var(--color-text-secondary)] mb-6">
            {successData.codigo === 'IDEMPOTENT_REPLAY'
              ? 'Tu compra ya se había registrado en el intento anterior; no se realizó ningún cobro adicional.'
              : 'Tu pedido ha sido procesado exitosamente.'}
          </p>
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-6 mb-6 text-left space-y-3">
            <div className="flex justify-between">
              <span className="font-sans text-sm text-[var(--color-text-secondary)]">Número de pedido</span>
              <span className="font-mono font-bold text-[var(--color-text-primary)]">#{successData.pedido_id}</span>
            </div>
            {successData.total && (
              <div className="flex justify-between">
                <span className="font-sans text-sm text-[var(--color-text-secondary)]">Total</span>
                <span className="font-mono font-bold text-[var(--color-text-primary)]">
                  {formatQ(successData.total)}
                </span>
              </div>
            )}
            {successData.estado && (
              <div className="flex justify-between items-center">
                <span className="font-sans text-sm text-[var(--color-text-secondary)]">Estado</span>
                <Badge variant="success">{successData.estado}</Badge>
              </div>
            )}
          </div>
          <div className="flex gap-3 justify-center">
            <Button variant="secondary" asChild>
              <Link to={`/orders/${successData.pedido_id}`}>Ver pedido</Link>
            </Button>
            <Button asChild>
              <Link to="/catalog">Seguir comprando</Link>
            </Button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <div className="max-w-5xl mx-auto px-4 py-8">
        <h1 className="font-display font-bold text-2xl text-[var(--color-text-primary)] text-center mb-6">
          Finalizar compra
        </h1>

        <StepIndicator current={step} />

        <div className="flex flex-col lg:flex-row gap-6">
          <div className="flex-1">
            {step === 1 && (
              <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-6">
                <h2 className="font-display font-semibold text-lg text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
                  <MapPin size={18} className="text-[var(--color-action)]" />
                  Dirección de envío
                </h2>
                {addresses.length === 0 ? (
                  <div className="text-center py-8">
                    <MapPin size={40} className="mx-auto mb-3 text-[var(--color-border-strong)]" />
                    <p className="font-sans text-sm text-[var(--color-text-secondary)] mb-4">
                      No tienes direcciones guardadas. Agrega una desde tu perfil.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {addresses.map((addr) => (
                      <label
                        key={addr.id}
                        className={cn(
                          'flex items-start gap-3 p-4 rounded-[var(--radius-md)] border-2 cursor-pointer transition-colors',
                          selectedAddress === addr.id
                            ? 'border-[var(--color-action)] bg-[var(--color-action)]/5'
                            : 'border-[var(--color-border)] hover:border-[var(--color-border-strong)]'
                        )}
                      >
                        <input
                          type="radio"
                          name="address"
                          value={addr.id}
                          checked={selectedAddress === addr.id}
                          onChange={() => setSelectedAddress(addr.id)}
                          className="mt-0.5 accent-[var(--color-action)]"
                        />
                        <div>
                          <p className="font-sans font-semibold text-sm text-[var(--color-text-primary)]">
                            {addr.linea1}
                          </p>
                          <p className="font-sans text-xs text-[var(--color-text-secondary)]">
                            {addr.municipio}, {addr.departamento}
                          </p>
                          {addr.es_predeterminada && (
                            <Badge variant="action" className="mt-1">Predeterminada</Badge>
                          )}
                        </div>
                      </label>
                    ))}
                  </div>
                )}
                <Button
                  size="md"
                  className="mt-5 w-full sm:w-auto"
                  disabled={!selectedAddress}
                  onClick={() => setStep(2)}
                >
                  Continuar <ChevronRight size={14} />
                </Button>
              </div>
            )}

            {step === 2 && (
              <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-6">
                <h2 className="font-display font-semibold text-lg text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
                  <CreditCard size={18} className="text-[var(--color-action)]" />
                  Método de pago
                </h2>
                <div className="space-y-3">
                  {PAYMENT_METHODS.map((pm) => {
                    const { Icon } = pm
                    return (
                      <label
                        key={pm.id}
                        className={cn(
                          'flex items-center gap-4 p-4 rounded-[var(--radius-md)] border-2 cursor-pointer transition-colors',
                          selectedPayment === pm.id
                            ? 'border-[var(--color-action)] bg-[var(--color-action)]/5'
                            : 'border-[var(--color-border)] hover:border-[var(--color-border-strong)]'
                        )}
                      >
                        <input
                          type="radio"
                          name="payment"
                          value={pm.id}
                          checked={selectedPayment === pm.id}
                          onChange={() => setSelectedPayment(pm.id)}
                          className="accent-[var(--color-action)]"
                        />
                        <Icon size={18} className={selectedPayment === pm.id ? 'text-[var(--color-action)]' : 'text-[var(--color-text-muted)]'} />
                        <span className="font-sans font-medium text-sm text-[var(--color-text-primary)]">
                          {pm.label}
                        </span>
                      </label>
                    )
                  })}
                </div>
                <div className="flex gap-3 mt-5">
                  <Button variant="secondary" onClick={() => setStep(1)}>
                    Atrás
                  </Button>
                  <Button onClick={() => setStep(3)}>
                    Continuar <ChevronRight size={14} />
                  </Button>
                </div>
              </div>
            )}

            {step === 3 && (
              <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-6 space-y-5">
                <h2 className="font-display font-semibold text-lg text-[var(--color-text-primary)] flex items-center gap-2">
                  <ClipboardList size={18} className="text-[var(--color-action)]" />
                  Confirmar pedido
                </h2>

                <div className="rounded-[var(--radius-md)] bg-[var(--color-background)] border border-[var(--color-border)] p-4 space-y-2">
                  <h3 className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                    Dirección de envío
                  </h3>
                  {addresses.find((a) => a.id === selectedAddress) && (
                    <p className="font-sans text-sm text-[var(--color-text-primary)]">
                      {addresses.find((a) => a.id === selectedAddress)?.linea1},{' '}
                      {addresses.find((a) => a.id === selectedAddress)?.municipio},{' '}
                      {addresses.find((a) => a.id === selectedAddress)?.departamento}
                    </p>
                  )}
                </div>

                <div className="rounded-[var(--radius-md)] bg-[var(--color-background)] border border-[var(--color-border)] p-4 space-y-2">
                  <h3 className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                    Método de pago
                  </h3>
                  {(() => {
                    const pm = PAYMENT_METHODS.find((p) => p.id === selectedPayment)
                    const { Icon } = pm || {}
                    return (
                      <p className="font-sans text-sm text-[var(--color-text-primary)] flex items-center gap-2">
                        {Icon && <Icon size={16} className="text-[var(--color-text-muted)]" />}
                        {pm?.label}
                      </p>
                    )
                  })()}
                </div>

                {error && (
                  <AvisoCheckout error={error} reintentando={submitting} onReintentar={handleConfirm} />
                )}

                {priceChanges.length > 0 && (
                  <div className="rounded-[var(--radius-md)] bg-[var(--color-warning,#f59e0b)]/10 border border-[var(--color-warning,#f59e0b)]/40 px-4 py-3">
                    <p className="text-sm font-sans font-semibold text-[var(--color-warning,#f59e0b)]">
                      {priceChanges.length === 1
                        ? 'El precio de un artículo cambió.'
                        : 'Los precios de algunos artículos cambiaron.'}
                    </p>
                    <p className="text-xs font-sans text-[var(--color-text-secondary)] mt-1">
                      El total muestra los precios actuales. Al confirmar aceptas estos valores.
                    </p>
                  </div>
                )}

                <div className="flex gap-3">
                  <Button variant="secondary" onClick={() => setStep(2)}>
                    Atrás
                  </Button>
                  <Button
                    size="md"
                    className="flex-1"
                    loading={submitting}
                    disabled={submitting || items.length === 0}
                    onClick={handleConfirm}
                  >
                    <CheckCircle size={16} /> Confirmar pedido
                  </Button>
                </div>
              </div>
            )}
          </div>

          {step < 3 && (
            <aside className="lg:w-80 shrink-0">
              <OrderSummary items={items} cart={cart} />
            </aside>
          )}
        </div>
      </div>
    </div>
  )
}
