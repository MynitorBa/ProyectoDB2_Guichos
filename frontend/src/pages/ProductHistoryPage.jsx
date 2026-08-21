import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Calendar, RotateCcw, Clock, User, AlertCircle } from 'lucide-react'
import { toast } from 'sonner'
import { getProductHistory, getProductStateAt } from '../api/products'
import { CategoryAttrPanel } from '../components/product/CategoryAttrPanel'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Skeleton } from '../components/ui/skeleton'
import { Separator } from '../components/ui/separator'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { formatQ, formatDate, formatDatetime } from '../lib/utils'
import { cn } from '../lib/utils'

const TIPO_META = {
  PRODUCTO_CREADO:        { variant: 'success', dot: 'bg-[var(--color-success)]',  label: 'Creado' },
  PRECIO_ACTUALIZADO:     { variant: 'action',  dot: 'bg-[var(--color-action)]',   label: 'Precio actualizado' },
  DESCRIPCION_ACTUALIZADA:{ variant: 'default', dot: 'bg-[var(--color-jade)]',     label: 'Descripción actualizada' },
  ATRIBUTOS_ACTUALIZADOS: { variant: 'jade',    dot: 'bg-[var(--color-jade)]',     label: 'Atributos actualizados' },
  DISPONIBILIDAD_CAMBIADA:{ variant: 'warning', dot: 'bg-amber-500',               label: 'Disponibilidad cambiada' },
  PRODUCTO_DESCONTINUADO: { variant: 'error',   dot: 'bg-[var(--color-error)]',    label: 'Descontinuado' },
}

function DiffValue({ antes, despues }) {
  if (antes === undefined && despues === undefined) return null
  const fmtVal = (v) => {
    if (v === null || v === undefined) return '—'
    if (typeof v === 'boolean') return v ? 'Sí' : 'No'
    if (typeof v === 'object') return JSON.stringify(v)
    return String(v)
  }
  return (
    <div className="flex flex-col gap-0.5 text-xs font-sans">
      {antes !== undefined && (
        <span className="line-through text-[var(--color-error)] bg-[var(--color-error)]/8 px-1.5 py-0.5 rounded w-fit">
          {fmtVal(antes)}
        </span>
      )}
      {despues !== undefined && (
        <span className="text-[var(--color-success)] bg-[var(--color-success)]/8 px-1.5 py-0.5 rounded w-fit font-semibold">
          {fmtVal(despues)}
        </span>
      )}
    </div>
  )
}

function EventDiff({ anterior, nuevo: nuevo_ }) {
  if (!anterior && !nuevo_) return null
  const keys = Array.from(
    new Set([...Object.keys(anterior || {}), ...Object.keys(nuevo_ || {})])
  )
  if (!keys.length) return null
  return (
    <div className="mt-2 space-y-1.5 border-l-2 border-[var(--color-border)] pl-3">
      {keys.map((key) => {
        const antes = anterior?.[key]
        const despues = nuevo_?.[key]
        if (JSON.stringify(antes) === JSON.stringify(despues)) return null
        return (
          <div key={key}>
            <p className="text-[10px] font-sans font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-0.5">
              {key.replace(/_/g, ' ')}
            </p>
            <DiffValue antes={antes} despues={despues} />
          </div>
        )
      })}
    </div>
  )
}

function TimelineEvent({ evento }) {
  const meta = TIPO_META[evento.tipo_evento] || { variant: 'default', dot: 'bg-[var(--color-border-strong)]', label: evento.tipo_evento }

  return (
    <div className="relative pl-8">
      <div
        className={cn(
          'absolute left-0 top-3 h-3 w-3 rounded-full border-2 border-[var(--color-surface)] shadow-sm',
          meta.dot
        )}
      />
      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-4 hover:border-[var(--color-border-strong)] transition-colors">
        <div className="flex items-start justify-between gap-2 flex-wrap mb-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant={meta.variant} className="shrink-0">
              {meta.label}
            </Badge>
            {evento.version && (
              <span className="font-mono text-[10px] text-[var(--color-text-muted)] bg-[var(--color-border)] px-1.5 py-0.5 rounded">
                v{evento.version}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1 text-[var(--color-text-muted)]">
              <User size={11} />
              <span className="text-xs font-sans">Admin</span>
            </div>
            <div className="flex items-center gap-1 text-[var(--color-text-muted)]">
              <Clock size={11} />
              <span className="text-xs font-sans">{formatDatetime(evento.timestamp)}</span>
            </div>
          </div>
        </div>

        <EventDiff anterior={evento.datos_anteriores} nuevo={evento.datos_nuevos} />
      </div>
    </div>
  )
}

function ReconstructedPanel({ estado, fecha }) {
  if (!estado) return null
  return (
    <div className="rounded-[var(--radius-lg)] border-2 border-[var(--color-jade)] bg-[var(--color-jade)]/5 overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-3 bg-[var(--color-jade)]/10 border-b border-[var(--color-jade)]/30">
        <Calendar size={15} className="text-[var(--color-jade)]" />
        <p className="font-sans text-sm font-semibold text-[var(--color-jade)]">
          Vista histórica — estado al {formatDate(fecha)}
        </p>
      </div>
      <div className="p-5 space-y-4">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <h3 className="font-display font-bold text-lg text-[var(--color-text-primary)]">
              {estado.nombre}
            </h3>
            {estado.sku && (
              <p className="font-mono text-xs text-[var(--color-text-muted)] mt-0.5">{estado.sku}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={estado.disponible ? 'success' : 'error'}>
              {estado.disponible ? 'Disponible' : 'No disponible'}
            </Badge>
            {estado.estado && (
              <Badge variant="default">{estado.estado}</Badge>
            )}
          </div>
        </div>

        <div>
          <span className="font-mono font-bold text-3xl text-[var(--color-text-primary)]">
            {formatQ(estado.precio)}
          </span>
          {estado.moneda && (
            <span className="font-sans text-xs text-[var(--color-text-muted)] ml-2">{estado.moneda}</span>
          )}
        </div>

        {estado.descripcion && (
          <p className="font-sans text-sm text-[var(--color-text-secondary)] leading-relaxed">
            {estado.descripcion}
          </p>
        )}

        {estado.atributos && estado.categoria && (
          <CategoryAttrPanel
            categoria={estado.categoria}
            atributos={estado.atributos}
          />
        )}

        {estado.atributos && Object.keys(estado.atributos).length > 0 && (
          <div>
            <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-2">
              Atributos
            </p>
            <div className="overflow-hidden rounded-[var(--radius-md)] border border-[var(--color-border)]">
              {Object.entries(estado.atributos).map(([key, value], idx, arr) => (
                <div
                  key={key}
                  className={cn(
                    'flex justify-between px-4 py-2 text-sm',
                    idx < arr.length - 1 ? 'border-b border-[var(--color-border)]' : '',
                    idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]'
                  )}
                >
                  <span className="font-sans text-[var(--color-text-secondary)] capitalize">
                    {key.replace(/_/g, ' ')}
                  </span>
                  <span className="font-sans font-medium text-[var(--color-text-primary)]">
                    {typeof value === 'boolean' ? (value ? 'Sí' : 'No') : String(value)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function ProductHistoryPage() {
  const { id } = useParams()
  const [fecha, setFecha] = useState('')
  const [reconstructDate, setReconstructDate] = useState('')
  const [reconstructed, setReconstructed] = useState(null)
  const [reconstructing, setReconstructing] = useState(false)
  const [reconstructError, setReconstructError] = useState('')

  const { data: historyData, isLoading, isError } = useQuery({
    queryKey: ['product-history', id],
    queryFn: () => getProductHistory(id).then((r) => r.data),
  })

  const eventos = historyData?.eventos || []
  const createdEvent = eventos.find((e) => e.tipo_evento === 'PRODUCTO_CREADO')
  const productName =
    createdEvent?.datos_nuevos?.nombre ||
    historyData?.producto_nombre ||
    `Producto ${id}`

  async function handleReconstruct(e) {
    e.preventDefault()
    if (!fecha) return
    setReconstructing(true)
    setReconstructError('')
    setReconstructed(null)
    try {
      const res = await getProductStateAt(id, fecha)
      setReconstructed(res.data)
      setReconstructDate(fecha)
    } catch (err) {
      const msg =
        err?.response?.data?.detail ||
        'No se pudo reconstruir el estado para esa fecha.'
      setReconstructError(msg)
      toast.error(msg)
    } finally {
      setReconstructing(false)
    }
  }

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <div className="max-w-6xl mx-auto px-4 py-8">
        <Button variant="ghost" size="sm" className="mb-5 -ml-2" asChild>
          <Link to="/admin">
            <ArrowLeft size={14} /> Panel admin
          </Link>
        </Button>

        <div className="mb-6">
          <h1 className="font-display font-bold text-2xl text-[var(--color-text-primary)]">
            Historial del producto
          </h1>
          <p className="font-mono text-xs text-[var(--color-text-muted)] mt-1">ID: {id}</p>
          {productName && (
            <p className="font-sans text-base text-[var(--color-text-secondary)] mt-0.5">
              {productName}
            </p>
          )}
        </div>

        <div className="flex flex-col lg:flex-row gap-6">
          <aside className="w-full lg:w-[40%] shrink-0">
            <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-4 sticky top-4">
              <h2 className="font-display font-semibold text-base text-[var(--color-text-primary)] mb-4">
                Línea de tiempo{' '}
                <span className="font-mono font-normal text-sm text-[var(--color-text-muted)]">
                  ({eventos.length})
                </span>
              </h2>

              {isLoading && (
                <div className="space-y-4">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="pl-8 relative">
                      <Skeleton className="absolute left-0 top-3 h-3 w-3 rounded-full" />
                      <Skeleton className="h-20 w-full" />
                    </div>
                  ))}
                </div>
              )}

              {isError && (
                <div className="flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--color-error)]/10 border border-[var(--color-error)]/30 px-4 py-3">
                  <AlertCircle size={14} className="text-[var(--color-error)]" />
                  <p className="text-sm font-sans text-[var(--color-error)]">
                    No se pudo cargar el historial.
                  </p>
                </div>
              )}

              {!isLoading && !isError && eventos.length === 0 && (
                <p className="font-sans text-sm text-[var(--color-text-muted)] text-center py-6">
                  Sin eventos registrados para este producto.
                </p>
              )}

              {!isLoading && eventos.length > 0 && (
                <div className="relative space-y-3 max-h-[70vh] overflow-y-auto pr-1">
                  <div className="absolute left-1.5 top-0 bottom-0 w-px bg-[var(--color-border)]" />
                  {eventos.map((evento) => (
                    <TimelineEvent key={evento._id} evento={evento} />
                  ))}
                </div>
              )}
            </div>
          </aside>

          <main className="flex-1 min-w-0 space-y-6">
            <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5">
              <h2 className="font-display font-semibold text-base text-[var(--color-text-primary)] mb-1 flex items-center gap-2">
                <RotateCcw size={16} className="text-[var(--color-action)]" />
                Reconstruir estado histórico
              </h2>
              <p className="font-sans text-xs text-[var(--color-text-muted)] mb-4">
                Selecciona una fecha para ver cómo era el producto en ese momento.
              </p>

              <form onSubmit={handleReconstruct} className="flex flex-wrap gap-3 items-end">
                <div className="flex-1 min-w-[180px]">
                  <Label htmlFor="fecha-reconstruir">Fecha</Label>
                  <Input
                    id="fecha-reconstruir"
                    type="date"
                    value={fecha}
                    onChange={(e) => setFecha(e.target.value)}
                    max={new Date().toISOString().split('T')[0]}
                  />
                </div>
                <Button type="submit" loading={reconstructing} disabled={!fecha}>
                  <Calendar size={14} /> Reconstruir
                </Button>
              </form>

              {reconstructError && (
                <div className="mt-3 flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--color-error)]/10 border border-[var(--color-error)]/30 px-4 py-3">
                  <AlertCircle size={14} className="text-[var(--color-error)] shrink-0" />
                  <p className="text-sm font-sans text-[var(--color-error)]">{reconstructError}</p>
                </div>
              )}
            </div>

            {reconstructed ? (
              <ReconstructedPanel estado={reconstructed} fecha={reconstructDate} />
            ) : (
              !reconstructError && (
                <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-8 flex flex-col items-center text-center">
                  <Calendar size={40} className="text-[var(--color-border-strong)] mb-3" />
                  <h3 className="font-display font-semibold text-base text-[var(--color-text-primary)] mb-1">
                    Sin selección de fecha
                  </h3>
                  <p className="font-sans text-sm text-[var(--color-text-secondary)] max-w-xs">
                    Selecciona una fecha en el panel de la izquierda y presiona "Reconstruir" para ver el estado histórico del producto.
                  </p>
                </div>
              )
            )}
          </main>
        </div>
      </div>
    </div>
  )
}
