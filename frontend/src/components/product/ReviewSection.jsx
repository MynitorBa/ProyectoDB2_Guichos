import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Star, MessageSquare, Store, ImagePlus, X, ChevronDown, ChevronUp, ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'
import { getReviews, createReview, createReply, uploadReviewImages, puedeOpinar, getMiVendedor } from '../../api/reviews'
import { useAuth } from '../../context/AuthContext'
import { Button } from '../ui/button'

const STATIC_BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1').replace(/\/api\/v1$/, '')

function imgUrl(path) {
  if (!path) return null
  if (path.startsWith('http')) return path
  return `${STATIC_BASE}${path}`
}

// ── Selector de estrellas ────────────────────────────────────────────────────

function StarSelector({ value, onChange }) {
  const [hover, setHover] = useState(0)
  return (
    <div className="flex gap-1.5">
      {[1,2,3,4,5].map(n => (
        <button
          key={n} type="button"
          onClick={() => onChange(n)}
          onMouseEnter={() => setHover(n)}
          onMouseLeave={() => setHover(0)}
          className="transition-transform hover:scale-110 active:scale-95"
        >
          <Star size={28} className={`transition-colors ${(hover || value) >= n ? 'fill-amber-400 text-amber-400' : 'text-gray-200'}`} />
        </button>
      ))}
    </div>
  )
}

// ── Barra de distribución ────────────────────────────────────────────────────

function DistribucionBar({ distribucion, total }) {
  return (
    <div className="space-y-1.5">
      {[5,4,3,2,1].map(n => {
        const count = distribucion?.[String(n)] || 0
        const pct   = total > 0 ? Math.round((count / total) * 100) : 0
        return (
          <div key={n} className="flex items-center gap-2.5 text-xs">
            <span className="w-3 text-right font-mono text-[var(--color-text-muted)]">{n}</span>
            <Star size={10} className="fill-amber-400 text-amber-400 shrink-0" />
            <div className="flex-1 h-1.5 bg-[var(--color-border)] rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${pct}%`, background: 'linear-gradient(90deg,#f59e0b,#fbbf24)' }}
              />
            </div>
            <span className="w-7 text-right text-[var(--color-text-muted)] font-mono">{count}</span>
          </div>
        )
      })}
    </div>
  )
}

// ── Grid de imágenes ─────────────────────────────────────────────────────────

function ImageGrid({ imagenes }) {
  const [ampliada, setAmpliada] = useState(null)
  if (!imagenes?.length) return null
  return (
    <>
      <div className={`grid gap-1.5 mt-2 ${imagenes.length === 1 ? 'grid-cols-1' : 'grid-cols-2'}`}>
        {imagenes.slice(0, 4).map((src, i) => (
          <button
            key={i} type="button"
            onClick={() => setAmpliada(imgUrl(src))}
            className="overflow-hidden rounded-xl border border-[var(--color-border)] aspect-square bg-[var(--color-surface)] hover:opacity-90 transition-opacity"
          >
            <img src={imgUrl(src)} alt="" className="w-full h-full object-cover" />
          </button>
        ))}
      </div>
      {ampliada && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4"
          onClick={() => setAmpliada(null)}
        >
          <img src={ampliada} alt="" className="max-w-full max-h-full rounded-2xl shadow-2xl" />
        </div>
      )}
    </>
  )
}

// ── Picker de imágenes (formulario) ─────────────────────────────────────────

function ImagePicker({ files, onChange }) {
  const inputRef = useRef(null)
  const previews = files.map(f => URL.createObjectURL(f))
  return (
    <div className="space-y-2">
      <p className="text-xs text-[var(--color-text-muted)]">Fotos (máx. 4 · jpg, png, webp)</p>
      <div className="flex gap-2 flex-wrap">
        {previews.map((src, i) => (
          <div key={i} className="relative w-16 h-16 rounded-xl overflow-hidden border border-[var(--color-border)]">
            <img src={src} alt="" className="w-full h-full object-cover" />
            <button
              type="button"
              onClick={() => onChange(files.filter((_, j) => j !== i))}
              className="absolute top-0.5 right-0.5 h-5 w-5 rounded-full bg-black/60 flex items-center justify-center text-white hover:bg-black/80 transition-colors"
            >
              <X size={10} />
            </button>
          </div>
        ))}
        {files.length < 4 && (
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="w-16 h-16 rounded-xl border-2 border-dashed border-[var(--color-border)] flex flex-col items-center justify-center gap-0.5 text-[var(--color-text-muted)] hover:border-[var(--color-action)] hover:text-[var(--color-action)] transition-colors"
          >
            <ImagePlus size={18} />
            <span className="text-[9px] font-medium">Agregar</span>
          </button>
        )}
      </div>
      <input
        ref={inputRef} type="file" multiple hidden
        accept=".jpg,.jpeg,.png,.webp"
        onChange={e => {
          const nuevos = Array.from(e.target.files || [])
          onChange([...files, ...nuevos].slice(0, 4))
          e.target.value = ''
        }}
      />
    </div>
  )
}

// ── Formulario de respuesta del vendedor ─────────────────────────────────────

function ReplyForm({ resenaId, productoRef, onDone }) {
  const [texto, setTexto] = useState('')
  const qc = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => createReply(resenaId, { texto }),
    onSuccess: () => {
      toast.success('Respuesta enviada.')
      setTexto('')
      onDone()
      qc.invalidateQueries({ queryKey: ['reviews', productoRef] })
    },
    onError: (err) => {
      toast.error(err.response?.data?.detail || 'No se pudo enviar la respuesta.')
    },
  })
  return (
    <div className="mt-3 rounded-xl border border-[var(--color-action)]/30 bg-[var(--color-action)]/5 p-3 space-y-2">
      <p className="text-xs font-semibold text-[var(--color-action)] flex items-center gap-1.5">
        <Store size={12} /> Respuesta oficial del vendedor
      </p>
      <textarea
        className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] p-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[var(--color-action)]/30"
        rows={2} value={texto}
        onChange={e => setTexto(e.target.value)}
        placeholder="Escribe tu respuesta al cliente..."
        autoFocus
      />
      <div className="flex gap-2">
        <Button size="sm" disabled={!texto.trim() || mutation.isPending} loading={mutation.isPending} onClick={() => mutation.mutate()}>
          Publicar respuesta
        </Button>
        <Button variant="ghost" size="sm" onClick={onDone}>Cancelar</Button>
      </div>
    </div>
  )
}

// ── Tarjeta de reseña ─────────────────────────────────────────────────────────

function ReviewCard({ r, myVendorId, productoRef }) {
  const [open, setOpen] = useState(false)
  const esVendedorDeEsta = myVendorId != null && myVendorId === r.vendedor_id
  const respuestas = r.respuestas || []

  return (
    <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden shadow-[0_1px_6px_rgba(0,0,0,0.04)]">
      <div className="p-4 space-y-3">
        {/* Cabecera */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div
              className="h-9 w-9 rounded-full flex items-center justify-center text-sm font-bold text-white shrink-0"
              style={{ background: 'linear-gradient(135deg,#29B6F6,#0288D1)' }}
            >
              {(r.usuario_nombre || '?')[0].toUpperCase()}
            </div>
            <div>
              <p className="text-sm font-semibold text-[var(--color-text-primary)] leading-tight">{r.usuario_nombre}</p>
              <div className="flex items-center gap-1.5 flex-wrap mt-0.5">
                {r.verificada && (
                  <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold text-emerald-600">
                    <ShieldCheck size={10} /> Compra verificada
                  </span>
                )}
                {r.vendedor_nombre && (
                  <span className="inline-flex items-center gap-1 text-[10px] font-medium text-[var(--color-text-muted)] bg-[var(--color-border)]/60 px-1.5 py-0.5 rounded-full">
                    <Store size={9} /> {r.vendedor_nombre}
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0">
            <div className="flex">
              {[1,2,3,4,5].map(n => (
                <Star key={n} size={13} className={r.calificacion >= n ? 'fill-amber-400 text-amber-400' : 'text-gray-200'} />
              ))}
            </div>
            <p className="text-[10px] text-[var(--color-text-muted)]">
              {new Date(r.fecha).toLocaleDateString('es-GT', { year:'numeric', month:'short', day:'numeric' })}
            </p>
          </div>
        </div>

        {/* Texto */}
        <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed">{r.texto}</p>

        {/* Imágenes */}
        <ImageGrid imagenes={r.imagenes} />
      </div>

      {/* Respuestas del vendedor */}
      {respuestas.length > 0 && (
        <div className="border-t border-[var(--color-border)] bg-[var(--color-action)]/4 px-4 py-3 space-y-3">
          {respuestas.map(rep => (
            <div key={rep.id} className="flex gap-2.5">
              <div
                className="h-7 w-7 rounded-full flex items-center justify-center shrink-0"
                style={{ background: 'linear-gradient(135deg,#29B6F6,#0288D1)' }}
              >
                <Store size={12} className="text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-bold text-[var(--color-action)]">{rep.autor_nombre}</span>
                  <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full text-white" style={{ background: 'linear-gradient(135deg,#29B6F6,#0288D1)' }}>Vendedor</span>
                  <span className="text-[10px] text-[var(--color-text-muted)]">
                    {new Date(rep.fecha).toLocaleDateString('es-GT', { month:'short', day:'numeric' })}
                  </span>
                </div>
                <p className="text-sm text-[var(--color-text-secondary)] mt-0.5 leading-relaxed">{rep.texto}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Botón responder — solo visible para el vendedor de esta reseña */}
      {esVendedorDeEsta && (
        <div className="border-t border-[var(--color-border)] px-4 pb-4">
          {!open ? (
            <button
              type="button"
              onClick={() => setOpen(true)}
              className="mt-3 flex items-center gap-1.5 text-xs font-semibold text-[var(--color-action)] hover:opacity-80 transition-opacity"
            >
              <MessageSquare size={13} />
              {respuestas.length > 0 ? 'Agregar otra respuesta' : 'Responder al cliente'}
            </button>
          ) : (
            <ReplyForm resenaId={r.id} productoRef={productoRef} onDone={() => setOpen(false)} />
          )}
        </div>
      )}
    </div>
  )
}

// ── Componente principal ─────────────────────────────────────────────────────

export default function ReviewSection({ productoRef, vendedorId }) {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [calificacion, setCalificacion] = useState(0)
  const [texto, setTexto] = useState('')
  const [imageFiles, setImageFiles] = useState([])
  const [mostrarForm, setMostrarForm] = useState(false)
  const [showAll, setShowAll] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['reviews', productoRef],
    queryFn: () => getReviews(productoRef).then(r => r.data),
    enabled: Boolean(productoRef),
  })

  const { data: puedeData, isLoading: puedeLoading } = useQuery({
    queryKey: ['puede-opinar', productoRef],
    queryFn: () => puedeOpinar(productoRef).then(r => r.data),
    enabled: Boolean(user && productoRef),
  })

  const { data: vendorData } = useQuery({
    queryKey: ['mi-vendedor'],
    queryFn: () => getMiVendedor().then(r => r.data),
    enabled: Boolean(user),
    staleTime: Infinity,
  })

  const myVendorId = vendorData?.vendedor_id ?? null

  const mutation = useMutation({
    mutationFn: async () => {
      const res = await createReview({ producto_ref: productoRef, vendedor_id: vendedorId, calificacion, texto })
      const resenaId = res.data.id
      if (imageFiles.length > 0) {
        const fd = new FormData()
        imageFiles.forEach(f => fd.append('archivos', f))
        await uploadReviewImages(resenaId, fd)
      }
      return res
    },
    onSuccess: (res) => {
      const estado = res?.data?.estado ?? 'aprobada'
      const razon  = res?.data?.razon_pendiente
      if (estado === 'pendiente') {
        const motivo = razon === 'bombardeo'
          ? 'Se detectó una cantidad inusual de reseñas recientes para este producto.'
          : 'Tu patrón de reseñas requiere revisión por el equipo de TiendaYa.'
        toast.warning(`Tu reseña está en revisión. ${motivo}`)
      } else {
        toast.success('Reseña publicada correctamente.')
      }
      setCalificacion(0); setTexto(''); setImageFiles([]); setMostrarForm(false)
      qc.invalidateQueries({ queryKey: ['reviews', productoRef] })
      qc.invalidateQueries({ queryKey: ['puede-opinar', productoRef] })
    },
    onError: (err) => {
      toast.error(err.response?.data?.detail || 'No se pudo enviar la reseña.')
    },
  })

  const resumen = data?.resumen
  const resenas = data?.resenas || []
  const visibles = showAll ? resenas : resenas.slice(0, 3)

  return (
    <div className="space-y-6">

      {/* ── Resumen ── */}
      {resumen && resumen.total > 0 && (
        <div className="flex gap-6 items-start p-5 rounded-2xl bg-[var(--color-surface)] border border-[var(--color-border)] shadow-[0_1px_8px_rgba(0,0,0,0.04)]">
          <div className="text-center shrink-0">
            <div className="font-mono font-black text-5xl leading-none" style={{ color: '#0277BD' }}>
              {resumen.promedio}
            </div>
            <div className="flex justify-center gap-0.5 mt-2">
              {[1,2,3,4,5].map(n => (
                <Star key={n} size={15} className={resumen.promedio >= n ? 'fill-amber-400 text-amber-400' : 'text-gray-200'} />
              ))}
            </div>
            <p className="text-xs text-[var(--color-text-muted)] mt-1.5 font-medium">
              {resumen.total} reseña{resumen.total !== 1 ? 's' : ''}
            </p>
          </div>
          <div className="flex-1">
            <DistribucionBar distribucion={resumen.distribucion} total={resumen.total} />
          </div>
        </div>
      )}

      {/* ── CTA escribir reseña ── */}
      {user && !mostrarForm && !puedeLoading && (
        puedeData?.puede ? (
          <button
            type="button"
            onClick={() => setMostrarForm(true)}
            className="w-full flex items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-[var(--color-border)] py-3.5 text-sm font-semibold text-[var(--color-text-muted)] hover:border-[var(--color-action)] hover:text-[var(--color-action)] transition-all duration-150"
          >
            <Star size={15} /> Escribir una reseña
          </button>
        ) : puedeData?.ya_reseno ? (
          <p className="text-center text-sm text-[var(--color-text-muted)] py-2">Ya dejaste una reseña para este producto.</p>
        ) : (
          <div className="flex items-center gap-2.5 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-sm text-[var(--color-text-muted)]">
            <ShieldCheck size={16} className="shrink-0 text-[var(--color-text-muted)]" />
            Compra este producto para poder dejar una reseña.
          </div>
        )
      )}

      {/* ── Formulario de reseña ── */}
      {mostrarForm && (
        <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 space-y-4 shadow-[0_4px_20px_rgba(41,182,246,0.08)]">
          <p className="font-display font-bold text-base text-[var(--color-text-primary)]">Tu reseña</p>

          <div className="space-y-1.5">
            <p className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Calificación</p>
            <StarSelector value={calificacion} onChange={setCalificacion} />
          </div>

          <div className="space-y-1.5">
            <p className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">Comentario</p>
            <textarea
              className="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-background)] p-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[var(--color-action)]/30 transition-shadow"
              rows={3} value={texto}
              onChange={e => setTexto(e.target.value)}
              placeholder="¿Qué te pareció el producto? (mín. 5 caracteres)"
            />
          </div>

          <ImagePicker files={imageFiles} onChange={setImageFiles} />

          <div className="flex gap-2 pt-1">
            <Button
              disabled={calificacion === 0 || texto.length < 5 || mutation.isPending}
              loading={mutation.isPending}
              onClick={() => mutation.mutate()}
            >
              Publicar reseña
            </Button>
            <Button variant="ghost" onClick={() => { setMostrarForm(false); setImageFiles([]) }}>
              Cancelar
            </Button>
          </div>
        </div>
      )}

      {/* ── Lista de reseñas ── */}
      {isLoading && (
        <div className="space-y-3">
          {[1,2].map(i => (
            <div key={i} className="rounded-2xl border border-[var(--color-border)] p-4 space-y-3 animate-pulse">
              <div className="flex gap-3">
                <div className="h-9 w-9 rounded-full bg-[var(--color-border)]" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3.5 w-28 rounded bg-[var(--color-border)]" />
                  <div className="h-3 w-20 rounded bg-[var(--color-border)]" />
                </div>
              </div>
              <div className="h-4 w-full rounded bg-[var(--color-border)]" />
              <div className="h-4 w-3/4 rounded bg-[var(--color-border)]" />
            </div>
          ))}
        </div>
      )}

      {!isLoading && resenas.length === 0 && (
        <div className="text-center py-10 space-y-2">
          <div className="mx-auto h-14 w-14 rounded-full bg-[var(--color-surface)] border border-[var(--color-border)] flex items-center justify-center">
            <Star size={24} className="text-gray-300" />
          </div>
          <p className="text-sm font-semibold text-[var(--color-text-primary)]">Sin reseñas aún</p>
          <p className="text-xs text-[var(--color-text-muted)]">Sé el primero en opinar sobre este producto.</p>
        </div>
      )}

      {!isLoading && resenas.length > 0 && (
        <div className="space-y-3">
          {visibles.map(r => (
            <ReviewCard key={r.id} r={r} myVendorId={myVendorId} productoRef={productoRef} />
          ))}

          {resenas.length > 3 && (
            <button
              type="button"
              onClick={() => setShowAll(v => !v)}
              className="w-full flex items-center justify-center gap-1.5 py-2.5 rounded-xl border border-[var(--color-border)] text-sm font-semibold text-[var(--color-text-secondary)] hover:border-[var(--color-action)] hover:text-[var(--color-action)] transition-all"
            >
              {showAll ? <><ChevronUp size={14}/> Ver menos</> : <><ChevronDown size={14}/> Ver las {resenas.length - 3} reseñas restantes</>}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
