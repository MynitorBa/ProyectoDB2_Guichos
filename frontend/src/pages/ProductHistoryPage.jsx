import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Calendar, RotateCcw, Clock, User, AlertCircle, TrendingUp } from 'lucide-react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { toast } from 'sonner'
import {
  getProductHistory,
  getProductPriceHistory,
  getProductStateAt,
} from '../api/products'
import { CategoryAttrPanel } from '../components/product/CategoryAttrPanel'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Skeleton } from '../components/ui/skeleton'
import { Separator } from '../components/ui/separator'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../components/ui/select'
import { formatQ, formatDate, formatDatetime } from '../lib/utils'
import { cn } from '../lib/utils'

const TIPO_META = {
  PRODUCTO_CREADO:        { variant: 'success', dot: 'bg-[var(--color-success)]',  label: 'Creado' },
  PRECIO_ACTUALIZADO:     { variant: 'action',  dot: 'bg-[var(--color-action)]',   label: 'Precio actualizado' },
  DESCRIPCION_ACTUALIZADA:{ variant: 'default', dot: 'bg-[var(--color-jade)]',     label: 'Descripción actualizada' },
  ATRIBUTOS_ACTUALIZADOS: { variant: 'jade',    dot: 'bg-[var(--color-jade)]',     label: 'Atributos actualizados' },
  ATRIBUTOS_RECONCILIADOS:{ variant: 'jade',    dot: 'bg-[var(--color-jade)]',     label: 'Atributos reconciliados' },
  DISPONIBILIDAD_CAMBIADA:{ variant: 'warning', dot: 'bg-amber-500',               label: 'Disponibilidad cambiada' },
  PRODUCTO_DESCONTINUADO: { variant: 'error',   dot: 'bg-[var(--color-error)]',    label: 'Descontinuado' },
  ESTADO_PRODUCTO_CAMBIADO:{ variant: 'warning', dot: 'bg-amber-500',               label: 'Estado del producto' },
  OFERTA_PRECIO_INICIAL:  { variant: 'action',  dot: 'bg-[var(--color-action)]',   label: 'Precio inicial de oferta' },
  OFERTA_PRECIO_ACTUALIZADO:{ variant: 'action', dot: 'bg-[var(--color-action)]',  label: 'Precio de oferta actualizado' },
  OFERTA_ESTADO_INICIAL:  { variant: 'default', dot: 'bg-slate-500',               label: 'Estado inicial de oferta' },
  OFERTA_ESTADO_CAMBIADO: { variant: 'warning', dot: 'bg-amber-500',               label: 'Estado de oferta cambiado' },
  INVENTARIO_SALDO_INICIAL:{ variant: 'default', dot: 'bg-cyan-600',               label: 'Inventario inicial' },
  INVENTARIO_SALDO_CAMBIADO:{ variant: 'jade', dot: 'bg-cyan-600',                 label: 'Inventario actualizado' },
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
            <Badge variant="secondary" className="shrink-0">
              {evento.fuente === 'mysql' ? 'MySQL' : 'MongoDB'}
            </Badge>
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
          Vista histórica — estado al {formatDatetime(fecha.length === 16 ? fecha + ':00' : fecha)}
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

        {estado.descripcion && (
          <p className="font-sans text-sm text-[var(--color-text-secondary)] leading-relaxed">
            {estado.descripcion}
          </p>
        )}

        <div>
          <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-2">
            Ofertas existentes en ese momento
          </p>
          {estado.ofertas?.length ? (
            <div className="space-y-2">
              {estado.ofertas.map((oferta) => (
                <div
                  key={oferta.oferta_id}
                  className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
                >
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div>
                      <p className="font-sans font-semibold text-sm text-[var(--color-text-primary)]">
                        {oferta.vendedor_nombre}
                      </p>
                      <p className="font-mono text-[11px] text-[var(--color-text-muted)]">
                        Oferta #{oferta.oferta_id} · {oferta.sku}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-mono font-bold text-xl text-[var(--color-text-primary)]">
                        {oferta.precio == null ? 'Sin precio registrado' : formatQ(oferta.precio)}
                      </p>
                      <p className="font-sans text-xs text-[var(--color-text-muted)]">
                        Stock: {oferta.stock} · Reservado: {oferta.stock_reservado}
                      </p>
                    </div>
                  </div>
                  <div className="flex gap-2 mt-2">
                    <Badge variant={oferta.disponible ? 'success' : 'error'}>
                      {oferta.disponible ? 'Disponible' : 'No disponible'}
                    </Badge>
                    <Badge variant="default">{oferta.estado}</Badge>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="font-sans text-sm text-[var(--color-text-muted)]">
              El producto todavía no tenía ofertas registradas en esa fecha.
            </p>
          )}
        </div>

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

const CHART_COLORS = ['#5b21b6', '#0891b2', '#16a34a', '#d97706', '#dc2626', '#7c3aed']

function PriceHistoryPanel({ data, isLoading, isError, range, setRange, onApply }) {
  const offers = data?.ofertas || []
  const labels = Object.fromEntries(
    offers.map((offer) => [
      `oferta_${offer.oferta_id}`,
      `${offer.vendedor_nombre} · #${offer.oferta_id}`,
    ])
  )
  const dates = new Map()
  offers.forEach((offer) => {
    offer.puntos.forEach((point) => {
      const row = dates.get(point.fecha) || { fecha: point.fecha }
      row[`oferta_${offer.oferta_id}`] = point.precio
      dates.set(point.fecha, row)
    })
  })
  const chartData = Array.from(dates.values()).sort((a, b) => a.fecha.localeCompare(b.fecha))

  return (
    <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5">
      <div className="flex items-start justify-between gap-4 flex-wrap mb-4">
        <div>
          <h2 className="font-display font-semibold text-base text-[var(--color-text-primary)] flex items-center gap-2">
            <TrendingUp size={16} className="text-[var(--color-action)]" />
            Histórico diario de precios
          </h2>
          <p className="font-sans text-xs text-[var(--color-text-muted)] mt-1">
            Una línea por oferta; se conserva el último precio vigente al cierre de cada día en Guatemala.
          </p>
        </div>
        <form onSubmit={onApply} className="flex items-end gap-2 flex-wrap">
          <div>
            <Label htmlFor="precio-desde">Desde</Label>
            <Input
              id="precio-desde"
              type="date"
              value={range.desde}
              onChange={(e) => setRange((current) => ({ ...current, desde: e.target.value }))}
            />
          </div>
          <div>
            <Label htmlFor="precio-hasta">Hasta</Label>
            <Input
              id="precio-hasta"
              type="date"
              value={range.hasta}
              onChange={(e) => setRange((current) => ({ ...current, hasta: e.target.value }))}
            />
          </div>
          <Button type="submit" variant="outline">Aplicar rango</Button>
        </form>
      </div>

      {isLoading && <Skeleton className="h-72 w-full" />}
      {isError && (
        <div className="flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--color-error)]/10 border border-[var(--color-error)]/30 px-4 py-3">
          <AlertCircle size={14} className="text-[var(--color-error)]" />
          <p className="text-sm font-sans text-[var(--color-error)]">No se pudo cargar el histórico de precios.</p>
        </div>
      )}
      {!isLoading && !isError && chartData.length > 0 && (
        <div className="h-80 w-full" aria-label="Gráfica del histórico diario de precios">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 10, right: 20, left: 5, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis dataKey="fecha" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={(value) => `Q${value}`} />
              <Tooltip formatter={(value, name) => [formatQ(value), labels[name] || name]} />
              <Legend formatter={(value) => labels[value] || value} />
              {offers.map((offer, index) => (
                <Line
                  key={offer.oferta_id}
                  type="stepAfter"
                  dataKey={`oferta_${offer.oferta_id}`}
                  stroke={CHART_COLORS[index % CHART_COLORS.length]}
                  strokeWidth={2}
                  dot={chartData.length <= 45}
                  connectNulls={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

export default function ProductHistoryPage() {
  const { id } = useParams()
  const [fecha, setFecha] = useState('')
  const [reconstructDate, setReconstructDate] = useState('')

  function maxDatetimeGT() {
    const now = new Date()
    const gt = new Intl.DateTimeFormat('sv-SE', {
      timeZone: 'America/Guatemala',
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hour12: false,
    }).format(now).replace(' ', 'T')
    return gt
  }
  const [reconstructed, setReconstructed] = useState(null)
  const [reconstructing, setReconstructing] = useState(false)
  const [reconstructError, setReconstructError] = useState('')
  const [priceRange, setPriceRange] = useState({ desde: '', hasta: '' })
  const [appliedPriceRange, setAppliedPriceRange] = useState({ desde: '', hasta: '' })
  const [timelineRange, setTimelineRange] = useState({ desde: '', hasta: '', fuente: 'todas' })
  const [appliedTimelineRange, setAppliedTimelineRange] = useState({ desde: '', hasta: '', fuente: 'todas' })

  const { data: historyData, isLoading, isError } = useQuery({
    queryKey: ['product-history', id, appliedTimelineRange],
    queryFn: () => getProductHistory(id, {
      ...(appliedTimelineRange.desde ? { desde: appliedTimelineRange.desde } : {}),
      ...(appliedTimelineRange.hasta ? { hasta: appliedTimelineRange.hasta } : {}),
      fuente: appliedTimelineRange.fuente,
    }).then((r) => r.data),
  })

  const {
    data: priceHistory,
    isLoading: isLoadingPrices,
    isError: isPriceError,
  } = useQuery({
    queryKey: ['product-price-history', id, appliedPriceRange],
    queryFn: () => getProductPriceHistory(id, {
      ...(appliedPriceRange.desde ? { desde: appliedPriceRange.desde } : {}),
      ...(appliedPriceRange.hasta ? { hasta: appliedPriceRange.hasta } : {}),
    }).then((r) => r.data),
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

  function handlePriceRange(e) {
    e.preventDefault()
    if (priceRange.desde && priceRange.hasta && priceRange.desde > priceRange.hasta) {
      toast.error('La fecha inicial no puede ser posterior a la fecha final.')
      return
    }
    setAppliedPriceRange(priceRange)
  }

  function handleTimelineRange(e) {
    e.preventDefault()
    if (timelineRange.desde && timelineRange.hasta && timelineRange.desde > timelineRange.hasta) {
      toast.error('La fecha inicial no puede ser posterior a la fecha final.')
      return
    }
    setAppliedTimelineRange(timelineRange)
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

        <div className="mb-6">
          <PriceHistoryPanel
            data={priceHistory}
            isLoading={isLoadingPrices}
            isError={isPriceError}
            range={priceRange}
            setRange={setPriceRange}
            onApply={handlePriceRange}
          />
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

              <form onSubmit={handleTimelineRange} className="space-y-2 mb-4 rounded-[var(--radius-md)] bg-[var(--color-background)] border border-[var(--color-border)] p-3">
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <Label htmlFor="timeline-desde">Desde</Label>
                    <Input id="timeline-desde" type="date" value={timelineRange.desde} onChange={(e) => setTimelineRange((current) => ({ ...current, desde: e.target.value }))} />
                  </div>
                  <div>
                    <Label htmlFor="timeline-hasta">Hasta</Label>
                    <Input id="timeline-hasta" type="date" value={timelineRange.hasta} onChange={(e) => setTimelineRange((current) => ({ ...current, hasta: e.target.value }))} />
                  </div>
                </div>
                <Select value={timelineRange.fuente} onValueChange={(value) => setTimelineRange((current) => ({ ...current, fuente: value }))}>
                  <SelectTrigger><SelectValue placeholder="Todas las fuentes" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="todas">MongoDB + MySQL</SelectItem>
                    <SelectItem value="mongodb">Solo producto (MongoDB)</SelectItem>
                    <SelectItem value="mysql">Solo ofertas e inventario (MySQL)</SelectItem>
                  </SelectContent>
                </Select>
                <Button type="submit" size="sm" variant="outline" className="w-full">Aplicar filtros</Button>
              </form>

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
                <div className="flex-1 min-w-[220px]">
                  <Label htmlFor="fecha-reconstruir">Fecha y hora (horario Guatemala)</Label>
                  <Input
                    id="fecha-reconstruir"
                    type="datetime-local"
                    value={fecha}
                    onChange={(e) => setFecha(e.target.value)}
                    max={maxDatetimeGT()}
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
