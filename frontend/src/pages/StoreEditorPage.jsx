import { useState, useEffect, useRef, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  GripVertical, Eye, EyeOff, Trash2, Plus, ChevronDown, ChevronUp,
  Save, ExternalLink, Monitor, Smartphone, Zap, Type, Image as ImageIcon,
  Minus, AlignLeft, AlignCenter, AlignRight, Loader2, Search as SearchIcon,
} from 'lucide-react'
import { getMyStoreConfig, saveMyStoreConfig } from '../api/store'
import { uploadRequestImage } from '../api/vendor'
import { useAuth } from '../context/AuthContext'
import StoreRenderer from '../components/store/StoreRenderer'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Separator } from '../components/ui/separator'
import { cn } from '../lib/utils'

// ── Constantes ────────────────────────────────────────────────────────────────
const FONTS = [
  'Inter', 'Plus Jakarta Sans', 'Playfair Display', 'Lora',
  'Raleway', 'Montserrat', 'Poppins', 'Merriweather', 'Nunito', 'DM Sans',
]

const SECTION_TYPES = [
  { tipo: 'hero',      label: 'Hero',      desc: 'Banner principal con imagen y llamada a acción', icon: ImageIcon  },
  { tipo: 'texto',     label: 'Texto',     desc: 'Bloque de título y texto libre',                icon: Type       },
  { tipo: 'productos', label: 'Productos', desc: 'Grilla de tus productos disponibles',            icon: Zap        },
  { tipo: 'buscador',  label: 'Buscador',  desc: 'Barra de búsqueda de productos de la tienda',   icon: SearchIcon },
  { tipo: 'separador', label: 'Separador', desc: 'Línea divisoria o espacio en blanco',            icon: Minus      },
]

const SECTION_DEFAULTS = {
  hero: {
    titulo: 'Bienvenido a nuestra tienda', subtitulo: '', imagen_url: '',
    alineacion: 'center', overlay_opacidad: 40, altura: 'md',
    botones: [{ id: 'btn-1', texto: 'Ver productos', accion: 'productos', url: '', estilo: 'principal' }],
  },
  texto:     { titulo: '', contenido: '', alineacion: 'center', tamano: 'md' },
  productos: { titulo: 'Nuestros productos', cantidad: 8 },
  buscador:  { placeholder: 'Buscar en nuestra tienda…', estilo: 'redondeado' },
  separador: { estilo: 'linea', alto: 'md' },
}

const DEFAULT_TEMA = {
  color_primario: '#0288D1', color_fondo: '#ffffff',
  color_texto: '#1a1a1a',   color_acento: '#f59e0b',
  fuente_titulos: 'Inter',  fuente_cuerpo: 'Inter',
  radio_bordes: 'md',       logo_url: '',
  logo_tamano: 'md',        logo_posicion: 'top-left',
  estilo_boton: 'degradado',
}


const INITIAL_SECCIONES = [
  { id: 'hero-default',      tipo: 'hero',      visible: true, config: { ...SECTION_DEFAULTS.hero } },
  { id: 'productos-default', tipo: 'productos', visible: true, config: { ...SECTION_DEFAULTS.productos } },
]

function uid() { return Math.random().toString(36).slice(2, 9) }

// ── Sección — panel de configuración por tipo ─────────────────────────────────
function HeroConfig({ cfg, onChange }) {
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef(null)

  async function handleImage(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const res = await uploadRequestImage(file)
      const url = res.data?.url || res.data?.imagen_url || ''
      onChange({ imagen_url: url })
    } catch { toast.error('No se pudo subir la imagen.') }
    finally { setUploading(false) }
  }

  const botones = cfg.botones || (cfg.boton_texto ? [{ id: 'btn-legacy', texto: cfg.boton_texto, accion: 'productos', url: '', estilo: 'principal' }] : [])

  function updateBtn(id, patch) { onChange({ botones: botones.map(b => b.id === id ? { ...b, ...patch } : b) }) }
  function removeBtn(id)        { onChange({ botones: botones.filter(b => b.id !== id) }) }
  function addBtn()             { onChange({ botones: [...botones, { id: uid(), texto: 'Más info', accion: 'url', url: '', estilo: 'contorno' }] }) }

  return (
    <div className="space-y-3 pt-1">
      <div className="space-y-1">
        <Label className="text-xs">Título</Label>
        <Input value={cfg.titulo || ''} onChange={e => onChange({ titulo: e.target.value })} placeholder="Bienvenido a nuestra tienda" />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Subtítulo</Label>
        <Input value={cfg.subtitulo || ''} onChange={e => onChange({ subtitulo: e.target.value })} placeholder="Descripción breve..." />
      </div>

      {/* ── Botones ── */}
      <div className="space-y-1.5">
        <Label className="text-xs">Botones del hero</Label>
        <div className="space-y-2">
          {botones.map((btn, i) => (
            <div key={btn.id} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] p-2.5 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-sans text-[10px] font-bold uppercase tracking-wider text-[var(--color-text-muted)]">
                  {i === 0 ? 'Botón principal' : `Botón ${i + 1}`}
                </span>
                <button onClick={() => removeBtn(btn.id)} className="text-[var(--color-text-muted)] hover:text-[var(--color-error)] transition-colors">
                  <Trash2 size={12} />
                </button>
              </div>
              <Input value={btn.texto} onChange={e => updateBtn(btn.id, { texto: e.target.value })} placeholder="Texto del botón" className="h-8 text-xs" />
              <div className="grid grid-cols-2 gap-1.5">
                <select value={btn.accion} onChange={e => updateBtn(btn.id, { accion: e.target.value })}
                  className="h-8 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-xs">
                  <option value="productos">↓ Ir a productos</option>
                  <option value="url">→ URL personalizada</option>
                  <option value="inicio">↑ Inicio de tienda</option>
                  <option value="catalogo">☰ Ver catálogo</option>
                </select>
                <select value={btn.estilo} onChange={e => updateBtn(btn.id, { estilo: e.target.value })}
                  className="h-8 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-xs">
                  <option value="principal">Principal</option>
                  <option value="degradado">Degradado</option>
                  <option value="contorno">Contorno</option>
                  <option value="pildora">Píldora</option>
                  <option value="brillo">Brillo</option>
                </select>
              </div>
              {btn.accion === 'url' && (
                <Input value={btn.url || ''} onChange={e => updateBtn(btn.id, { url: e.target.value })}
                  placeholder="https://..." className="h-8 text-xs font-mono" />
              )}
            </div>
          ))}
          {botones.length < 3 && (
            <button onClick={addBtn}
              className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg border border-dashed border-[var(--color-border)] text-xs text-[var(--color-text-muted)] hover:border-[var(--color-action)] hover:text-[var(--color-action)] transition-all">
              <Plus size={12} /> Agregar botón
            </button>
          )}
        </div>
      </div>

      <div className="space-y-1">
        <Label className="text-xs">Alineación</Label>
        <div className="flex gap-1">
          {[['left','Izq.'],['center','Centro'],['right','Der.']].map(([v,l]) => (
            <button key={v} onClick={() => onChange({ alineacion: v })}
              className={cn('flex-1 py-1.5 rounded text-xs border transition-all', cfg.alineacion === v ? 'bg-[var(--color-action)] text-white border-[var(--color-action)]' : 'border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-action)]')}>
              {l}
            </button>
          ))}
        </div>
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Altura del hero</Label>
        <select value={cfg.altura || 'md'} onChange={e => onChange({ altura: e.target.value })}
          className="w-full h-9 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-sm">
          <option value="baja">Baja (240px)</option>
          <option value="md">Media (380px)</option>
          <option value="alta">Alta (520px)</option>
        </select>
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Imagen de fondo</Label>
        <div className="flex gap-2 items-center">
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleImage} />
          <Button variant="secondary" size="sm" className="w-full" loading={uploading} onClick={() => fileRef.current?.click()}>
            <ImageIcon size={13} /> {cfg.imagen_url ? 'Cambiar imagen' : 'Subir imagen'}
          </Button>
          {cfg.imagen_url && (
            <Button variant="ghost" size="sm" onClick={() => onChange({ imagen_url: '' })}>
              <Trash2 size={13} />
            </Button>
          )}
        </div>
        {cfg.imagen_url && (
          <img src={cfg.imagen_url} alt="hero" className="w-full h-20 object-cover rounded mt-1 border border-[var(--color-border)]" />
        )}
      </div>
      {cfg.imagen_url && (
        <div className="space-y-1">
          <Label className="text-xs">Opacidad overlay ({cfg.overlay_opacidad ?? 40}%)</Label>
          <input type="range" min={0} max={80} value={cfg.overlay_opacidad ?? 40}
            onChange={e => onChange({ overlay_opacidad: Number(e.target.value) })}
            className="w-full accent-[var(--color-action)]" />
        </div>
      )}
    </div>
  )
}

function TextoConfig({ cfg, onChange }) {
  return (
    <div className="space-y-3 pt-1">
      <div className="space-y-1">
        <Label className="text-xs">Título</Label>
        <Input value={cfg.titulo || ''} onChange={e => onChange({ titulo: e.target.value })} placeholder="Sobre nosotros..." />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Contenido</Label>
        <textarea value={cfg.contenido || ''} onChange={e => onChange({ contenido: e.target.value })}
          rows={4} placeholder="Escribe aquí..."
          className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[var(--color-action)]/30" />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Alineación</Label>
        <div className="flex gap-1">
          {[['left', AlignLeft],['center', AlignCenter],['right', AlignRight]].map(([v, Icon]) => (
            <button key={v} onClick={() => onChange({ alineacion: v })}
              className={cn('flex-1 py-1.5 rounded border flex items-center justify-center transition-all', cfg.alineacion === v ? 'bg-[var(--color-action)] text-white border-[var(--color-action)]' : 'border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-action)]')}>
              <Icon size={14} />
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function ProductosConfig({ cfg, onChange }) {
  return (
    <div className="space-y-3 pt-1">
      <div className="space-y-1">
        <Label className="text-xs">Título de la sección</Label>
        <Input value={cfg.titulo || ''} onChange={e => onChange({ titulo: e.target.value })} placeholder="Nuestros productos" />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Cantidad a mostrar</Label>
        <select value={cfg.cantidad || 8} onChange={e => onChange({ cantidad: Number(e.target.value) })}
          className="w-full h-9 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-sm">
          <option value={4}>4 productos</option>
          <option value={8}>8 productos</option>
          <option value={12}>12 productos</option>
        </select>
      </div>
    </div>
  )
}

function SeparadorConfig({ cfg, onChange }) {
  return (
    <div className="space-y-3 pt-1">
      <div className="space-y-1">
        <Label className="text-xs">Estilo</Label>
        <select value={cfg.estilo || 'linea'} onChange={e => onChange({ estilo: e.target.value })}
          className="w-full h-9 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-sm">
          <option value="linea">Línea</option>
          <option value="espacio">Espacio en blanco</option>
        </select>
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Alto</Label>
        <select value={cfg.alto || 'md'} onChange={e => onChange({ alto: e.target.value })}
          className="w-full h-9 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-sm">
          <option value="bajo">Bajo</option>
          <option value="md">Medio</option>
          <option value="alto">Alto</option>
        </select>
      </div>
    </div>
  )
}

function BuscadorConfig({ cfg, onChange }) {
  const estilos = [
    { value: 'minimalista', label: 'Minimalista', desc: 'Solo línea inferior' },
    { value: 'cuadrado',    label: 'Cuadrado',    desc: 'Caja con borde' },
    { value: 'redondeado',  label: 'Redondeado',  desc: 'Forma píldora' },
    { value: 'con_boton',   label: 'Con botón',   desc: 'Input + botón buscar' },
  ]
  return (
    <div className="space-y-3 pt-1">
      <div className="space-y-1">
        <Label className="text-xs">Texto de ayuda (placeholder)</Label>
        <Input value={cfg.placeholder || ''} onChange={e => onChange({ placeholder: e.target.value })} placeholder="Buscar en nuestra tienda…" />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">Estilo del buscador</Label>
        <div className="space-y-1.5">
          {estilos.map(({ value, label, desc }) => (
            <button key={value} onClick={() => onChange({ estilo: value })}
              className={cn('w-full flex items-center justify-between px-3 py-2 rounded-lg border text-left transition-all',
                cfg.estilo === value
                  ? 'border-[var(--color-action)] bg-[var(--color-action)]/5'
                  : 'border-[var(--color-border)] hover:border-[var(--color-action)]/50')}>
              <div>
                <p className={cn('font-sans text-xs font-medium', cfg.estilo === value ? 'text-[var(--color-action)]' : 'text-[var(--color-text-primary)]')}>{label}</p>
                <p className="font-sans text-[10px] text-[var(--color-text-muted)]">{desc}</p>
              </div>
              {cfg.estilo === value && <div className="h-2 w-2 rounded-full bg-[var(--color-action)] flex-shrink-0" />}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

const SECTION_CONFIG_MAP = { hero: HeroConfig, texto: TextoConfig, productos: ProductosConfig, buscador: BuscadorConfig, separador: SeparadorConfig }

// ── Helpers de posición del logo ─────────────────────────────────────────────
const LOGO_POSITIONS = [
  { value: 'top-left',    row: 0, col: 0 },
  { value: 'top-center',  row: 0, col: 1 },
  { value: 'top-right',   row: 0, col: 2 },
  { value: 'mid-left',    row: 1, col: 0 },
  { value: 'mid-center',  row: 1, col: 1 },
  { value: 'mid-right',   row: 1, col: 2 },
  { value: 'bot-left',    row: 2, col: 0 },
  { value: 'bot-center',  row: 2, col: 1 },
  { value: 'bot-right',   row: 2, col: 2 },
]

const LOGO_SIZES = [
  { value: 'sm', label: 'S',   px: 36 },
  { value: 'md', label: 'M',   px: 64 },
  { value: 'lg', label: 'L',   px: 100 },
  { value: 'xl', label: 'XL',  px: 150 },
]

// ── LogoUpload ────────────────────────────────────────────────────────────────
function LogoUpload({ tema, onChangeTema }) {
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef(null)

  async function handleFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const res = await uploadRequestImage(file)
      const url = res.data?.url || res.data?.imagen_url || ''
      onChangeTema({ logo_url: url })
    } catch { toast.error('No se pudo subir el logo.') }
    finally { setUploading(false); e.target.value = '' }
  }

  const posicion = tema.logo_posicion || 'top-left'
  const tamano   = tema.logo_tamano   || 'md'

  return (
    <div className="space-y-3">
      <p className="font-sans text-xs font-bold uppercase tracking-wider text-[var(--color-text-muted)]">Logo de la tienda</p>

      {/* Upload / preview */}
      {tema.logo_url ? (
        <div className="flex items-center gap-3">
          <div className="h-14 w-28 rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] flex items-center justify-center overflow-hidden flex-shrink-0">
            <img src={tema.logo_url} alt="Logo" className="max-h-12 max-w-full object-contain" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Button variant="secondary" size="sm" loading={uploading} onClick={() => fileRef.current?.click()}>
              <ImageIcon size={12} /> Cambiar
            </Button>
            <Button variant="ghost" size="sm" className="text-[var(--color-error)] hover:text-[var(--color-error)]"
              onClick={() => onChangeTema({ logo_url: '' })}>
              <Trash2 size={12} /> Quitar
            </Button>
          </div>
        </div>
      ) : (
        <button onClick={() => fileRef.current?.click()}
          className="w-full flex flex-col items-center justify-center gap-2 py-5 rounded-lg border-2 border-dashed border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-action)] hover:text-[var(--color-action)] transition-all">
          {uploading ? <Loader2 size={20} className="animate-spin" /> : <ImageIcon size={20} />}
          <span className="font-sans text-xs">{uploading ? 'Subiendo…' : 'Subir logo'}</span>
        </button>
      )}
      <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleFile} />

      {/* Tamaño y posición — solo si hay logo */}
      {tema.logo_url && (
        <>
          {/* Tamaño */}
          <div className="space-y-1.5">
            <Label className="text-xs font-normal">Tamaño</Label>
            <div className="grid grid-cols-4 gap-1.5">
              {LOGO_SIZES.map(({ value, label, px }) => (
                <button key={value} onClick={() => onChangeTema({ logo_tamano: value })}
                  className={cn('py-1.5 rounded-lg border text-xs font-semibold transition-all flex flex-col items-center gap-0.5',
                    tamano === value
                      ? 'border-[var(--color-action)] bg-[var(--color-action)] text-white'
                      : 'border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-action)]')}>
                  {label}
                  <span className="font-normal opacity-70" style={{ fontSize: '9px' }}>{px}px</span>
                </button>
              ))}
            </div>
          </div>

          {/* Posición — grid 3×3 */}
          <div className="space-y-1.5">
            <Label className="text-xs font-normal">Posición en el hero</Label>
            <div
              className="inline-grid gap-1 rounded-lg border border-[var(--color-border)] p-2 bg-[var(--color-background)]"
              style={{ gridTemplateColumns: 'repeat(3, 2rem)', gridTemplateRows: 'repeat(3, 2rem)' }}
            >
              {LOGO_POSITIONS.map(({ value, row, col }) => {
                const active = posicion === value
                return (
                  <button
                    key={value}
                    title={value.replace('-', ' ')}
                    onClick={() => onChangeTema({ logo_posicion: value })}
                    style={{ gridRow: row + 1, gridColumn: col + 1 }}
                    className={cn(
                      'rounded-md flex items-center justify-center transition-all border',
                      active
                        ? 'bg-[var(--color-action)] border-[var(--color-action)]'
                        : 'border-[var(--color-border)] hover:border-[var(--color-action)] hover:bg-[var(--color-action)]/10'
                    )}
                  >
                    <span
                      className="rounded-full"
                      style={{
                        width: active ? '8px' : '5px',
                        height: active ? '8px' : '5px',
                        backgroundColor: active ? '#fff' : 'var(--color-text-muted)',
                        transition: 'all .15s',
                      }}
                    />
                  </button>
                )
              })}
            </div>
          </div>
        </>
      )}

      <p className="font-sans text-[10px] text-[var(--color-text-muted)]">
        PNG con fondo transparente recomendado.
      </p>
    </div>
  )
}

// ── SectionItem ───────────────────────────────────────────────────────────────
function SectionItem({ seccion, index, total, expanded, onToggleExpand, onToggleVisible, onDelete, onChangeConfig, onDragStart, onDragOver, onDrop, isDragOver }) {
  const meta = SECTION_TYPES.find(t => t.tipo === seccion.tipo) || SECTION_TYPES[0]
  const Icon = meta.icon
  const ConfigComp = SECTION_CONFIG_MAP[seccion.tipo]

  return (
    <div
      onDragOver={e => { e.preventDefault(); onDragOver(index) }}
      onDrop={onDrop}
      className={cn('rounded-lg border transition-all', isDragOver ? 'border-[var(--color-action)] bg-[var(--color-action)]/5' : 'border-[var(--color-border)] bg-[var(--color-surface)]')}
    >
      {/* Header de la sección */}
      <div className="flex items-center gap-2 px-3 py-2.5">
        <div
          draggable
          onDragStart={() => onDragStart(index)}
          title="Arrastrar para reordenar"
          className="cursor-grab active:cursor-grabbing text-[var(--color-text-muted)] touch-none p-1 -m-1 rounded hover:bg-[var(--color-border)] transition-colors"
        >
          <GripVertical size={16} />
        </div>
        <div className="h-7 w-7 rounded-md flex items-center justify-center flex-shrink-0"
          style={{ backgroundColor: 'var(--color-action)', opacity: seccion.visible === false ? 0.4 : 1 }}>
          <Icon size={13} className="text-white" />
        </div>
        <span className={cn('font-sans text-sm font-medium flex-1 truncate', seccion.visible === false && 'opacity-40')}>
          {meta.label}
          {seccion.config?.titulo && <span className="ml-1.5 font-normal text-[var(--color-text-muted)] text-xs truncate">· {seccion.config.titulo}</span>}
        </span>
        <div className="flex items-center gap-1 flex-shrink-0">
          <button onClick={onToggleVisible} title={seccion.visible === false ? 'Mostrar' : 'Ocultar'}
            className="h-7 w-7 flex items-center justify-center rounded text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-border)] transition-colors">
            {seccion.visible === false ? <EyeOff size={13} /> : <Eye size={13} />}
          </button>
          <button onClick={onDelete} title="Eliminar sección"
            className="h-7 w-7 flex items-center justify-center rounded text-[var(--color-text-muted)] hover:text-[var(--color-error)] hover:bg-[var(--color-error)]/10 transition-colors">
            <Trash2 size={13} />
          </button>
          <button onClick={onToggleExpand}
            className="h-7 w-7 flex items-center justify-center rounded text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors">
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      </div>
      {/* Panel de config expandible */}
      {expanded && ConfigComp && (
        <div className="px-3 pb-3 border-t border-[var(--color-border)]">
          <ConfigComp cfg={seccion.config || {}} onChange={patch => onChangeConfig(patch)} />
        </div>
      )}
    </div>
  )
}

// ── AddSectionModal ───────────────────────────────────────────────────────────
function AddSectionModal({ onAdd, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40" onClick={onClose}>
      <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] shadow-xl p-5 w-full max-w-sm space-y-3" onClick={e => e.stopPropagation()}>
        <h3 className="font-display font-semibold text-base">Agregar sección</h3>
        <div className="space-y-2">
          {SECTION_TYPES.map(({ tipo, label, desc, icon: Icon }) => (
            <button key={tipo} onClick={() => { onAdd(tipo); onClose() }}
              className="w-full flex items-start gap-3 p-3 rounded-lg border border-[var(--color-border)] text-left hover:border-[var(--color-action)] hover:bg-[var(--color-action)]/5 transition-all group">
              <div className="h-8 w-8 rounded-md flex items-center justify-center flex-shrink-0 mt-0.5"
                style={{ backgroundColor: 'var(--color-action)' }}>
                <Icon size={15} className="text-white" />
              </div>
              <div>
                <p className="font-sans text-sm font-semibold text-[var(--color-text-primary)] group-hover:text-[var(--color-action)]">{label}</p>
                <p className="font-sans text-xs text-[var(--color-text-muted)]">{desc}</p>
              </div>
            </button>
          ))}
        </div>
        <Button variant="secondary" size="sm" className="w-full" onClick={onClose}>Cancelar</Button>
      </div>
    </div>
  )
}

// ── StoreEditorPage ───────────────────────────────────────────────────────────
export default function StoreEditorPage() {
  const { user } = useAuth()
  const cache = useQueryClient()

  const [config, setConfig] = useState({ tema: { ...DEFAULT_TEMA }, secciones: INITIAL_SECCIONES })
  const [activeTab, setActiveTab] = useState('secciones')
  const [expandedId, setExpandedId] = useState(null)
  const [previewMode, setPreviewMode] = useState('desktop')
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showAddModal, setShowAddModal] = useState(false)
  const [dragIndex, setDragIndex] = useState(null)
  const [dropIndex, setDropIndex] = useState(null)
  const [vendedorId, setVendedorId] = useState(null)
  const initialized = useRef(false)

  // React Query v5 eliminó onSuccess — se inicializa via useEffect con ref guard
  // para no pisar ediciones del usuario cuando React Query revalida en background
  const { data: savedConfig, isLoading } = useQuery({
    queryKey: ['my-store-config'],
    queryFn: () => getMyStoreConfig().then(r => r.data),
  })

  useEffect(() => {
    if (!savedConfig || initialized.current) return
    initialized.current = true
    setConfig({
      tema: { ...DEFAULT_TEMA, ...(savedConfig.tema || {}) },
      secciones: savedConfig.secciones?.length ? savedConfig.secciones : INITIAL_SECCIONES,
    })
    if (savedConfig.vendedor_id) setVendedorId(savedConfig.vendedor_id)
  }, [savedConfig])

  // Persist draft to localStorage
  useEffect(() => {
    if (!dirty) return
    try { localStorage.setItem('store-editor-draft', JSON.stringify(config)) } catch {}
  }, [config, dirty])

  // ── Helpers ───────────────────────────────────────────────────────────────
  const updateTema = useCallback((patch) => {
    setConfig(c => ({ ...c, tema: { ...c.tema, ...patch } }))
    setDirty(true)
  }, [])

  const updateSecciones = useCallback((newSecs) => {
    setConfig(c => ({ ...c, secciones: newSecs }))
    setDirty(true)
  }, [])

  function addSection(tipo) {
    const newSec = { id: uid(), tipo, visible: true, config: { ...SECTION_DEFAULTS[tipo] } }
    updateSecciones([...config.secciones, newSec])
    setExpandedId(newSec.id)
  }

  function deleteSection(id) {
    updateSecciones(config.secciones.filter(s => s.id !== id))
    if (expandedId === id) setExpandedId(null)
  }

  function toggleVisible(id) {
    updateSecciones(config.secciones.map(s => s.id === id ? { ...s, visible: s.visible === false ? true : false } : s))
  }

  function updateSectionConfig(id, patch) {
    updateSecciones(config.secciones.map(s => s.id === id ? { ...s, config: { ...s.config, ...patch } } : s))
  }

  function handleDrop() {
    if (dragIndex === null || dropIndex === null || dragIndex === dropIndex) {
      setDragIndex(null); setDropIndex(null); return
    }
    const next = [...config.secciones]
    const [moved] = next.splice(dragIndex, 1)
    next.splice(dropIndex, 0, moved)
    updateSecciones(next)
    setDragIndex(null); setDropIndex(null)
  }

  async function handleSave() {
    setSaving(true)
    try {
      await saveMyStoreConfig(config)
      cache.invalidateQueries({ queryKey: ['my-store-config'] })
      setDirty(false)
      toast.success('Tienda guardada.')
      try { localStorage.removeItem('store-editor-draft') } catch {}
    } catch (e) {
      toast.error(e.response?.data?.detail || 'No se pudo guardar.')
    } finally { setSaving(false) }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen gap-3 text-[var(--color-text-muted)]">
        <Loader2 size={20} className="animate-spin" /> Cargando editor…
      </div>
    )
  }

  return (
    <div className="flex h-[calc(100vh-56px)] overflow-hidden bg-[var(--color-background)]">

      {/* ── Panel izquierdo ── */}
      <aside className="w-[340px] flex-shrink-0 flex flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden">

        {/* Header */}
        <div className="px-4 py-3 border-b border-[var(--color-border)] flex items-center justify-between gap-2 flex-shrink-0">
          <div>
            <h1 className="font-display font-bold text-sm text-[var(--color-text-primary)]">Editor de tienda</h1>
            {dirty && <p className="font-sans text-[10px] text-amber-500 font-medium">Cambios sin guardar</p>}
          </div>
          <div className="flex items-center gap-1.5">
            {vendedorId && (
              <Link to={`/tienda/${vendedorId}`} target="_blank"
                className="h-8 w-8 flex items-center justify-center rounded-md border border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-action)] hover:border-[var(--color-action)] transition-all" title="Ver tienda pública">
                <ExternalLink size={13} />
              </Link>
            )}
            <Button size="sm" loading={saving} onClick={handleSave} className="gap-1.5">
              <Save size={13} /> Guardar
            </Button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-[var(--color-border)] flex-shrink-0">
          {[['tema', 'Tema'], ['secciones', 'Secciones']].map(([k, l]) => (
            <button key={k} onClick={() => setActiveTab(k)}
              className={cn('flex-1 py-2.5 font-sans text-xs font-semibold transition-colors', activeTab === k ? 'text-[var(--color-action)] border-b-2 border-[var(--color-action)]' : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]')}>
              {l}
            </button>
          ))}
        </div>

        {/* Contenido scrollable */}
        <div className="flex-1 overflow-y-auto">

          {/* ── Tab Tema ── */}
          {activeTab === 'tema' && (
            <div className="p-4 space-y-5">
              {/* Colores */}
              <div className="space-y-3">
                <p className="font-sans text-xs font-bold uppercase tracking-wider text-[var(--color-text-muted)]">Colores</p>
                {[
                  ['color_primario', 'Color primario'],
                  ['color_fondo',    'Fondo de página'],
                  ['color_texto',    'Color de texto'],
                  ['color_acento',   'Color de acento'],
                ].map(([key, label]) => (
                  <div key={key} className="flex items-center justify-between gap-3">
                    <Label className="text-xs font-normal">{label}</Label>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-[var(--color-text-muted)]">{config.tema[key]}</span>
                      <label className="cursor-pointer">
                        <input type="color" value={config.tema[key] || '#000000'}
                          onChange={e => updateTema({ [key]: e.target.value })}
                          className="sr-only" />
                        <div className="h-7 w-9 rounded-md border-2 border-[var(--color-border)] shadow-sm cursor-pointer hover:scale-105 transition-transform"
                          style={{ backgroundColor: config.tema[key] || '#000' }} />
                      </label>
                    </div>
                  </div>
                ))}
              </div>

              <Separator />

              {/* Fuentes */}
              <div className="space-y-3">
                <p className="font-sans text-xs font-bold uppercase tracking-wider text-[var(--color-text-muted)]">Fuentes</p>
                {[['fuente_titulos', 'Títulos'], ['fuente_cuerpo', 'Cuerpo']].map(([key, label]) => (
                  <div key={key} className="space-y-1">
                    <Label className="text-xs font-normal">{label}</Label>
                    <select value={config.tema[key] || 'Inter'} onChange={e => updateTema({ [key]: e.target.value })}
                      className="w-full h-9 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-sm">
                      {FONTS.map(f => <option key={f} value={f}>{f}</option>)}
                    </select>
                  </div>
                ))}
              </div>

              <Separator />

              {/* Bordes */}
              <div className="space-y-2">
                <p className="font-sans text-xs font-bold uppercase tracking-wider text-[var(--color-text-muted)]">Bordes</p>
                <div className="grid grid-cols-4 gap-1.5">
                  {[['none','Sin'], ['sm','Suave'], ['md','Medio'], ['lg','Redondo']].map(([v, l]) => (
                    <button key={v} onClick={() => updateTema({ radio_bordes: v })}
                      className={cn('py-1.5 text-xs border rounded-lg transition-all', config.tema.radio_bordes === v ? 'bg-[var(--color-action)] text-white border-[var(--color-action)]' : 'border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-action)]')}>
                      {l}
                    </button>
                  ))}
                </div>
              </div>

              <Separator />

              {/* Logo */}
              <LogoUpload tema={config.tema} onChangeTema={updateTema} />

            </div>
          )}

          {/* ── Tab Secciones ── */}
          {activeTab === 'secciones' && (
            <div className="p-4 space-y-2">
              {config.secciones.length === 0 && (
                <p className="font-sans text-xs text-[var(--color-text-muted)] text-center py-6">
                  Sin secciones. Agrega la primera.
                </p>
              )}
              {config.secciones.map((sec, i) => (
                <SectionItem
                  key={sec.id}
                  seccion={sec}
                  index={i}
                  total={config.secciones.length}
                  expanded={expandedId === sec.id}
                  onToggleExpand={() => setExpandedId(prev => prev === sec.id ? null : sec.id)}
                  onToggleVisible={() => toggleVisible(sec.id)}
                  onDelete={() => deleteSection(sec.id)}
                  onChangeConfig={patch => updateSectionConfig(sec.id, patch)}
                  onDragStart={idx => setDragIndex(idx)}
                  onDragOver={idx => setDropIndex(idx)}
                  onDrop={handleDrop}
                  isDragOver={dropIndex === i && dragIndex !== i}
                />
              ))}
              <button onClick={() => setShowAddModal(true)}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg border-2 border-dashed border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-action)] hover:text-[var(--color-action)] transition-all text-sm font-sans font-medium mt-2">
                <Plus size={15} /> Agregar sección
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* ── Panel derecho: preview ── */}
      <div className="flex-1 flex flex-col overflow-hidden bg-[var(--color-background)]">

        {/* Toolbar de preview */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--color-border)] bg-[var(--color-surface)] flex-shrink-0">
          <span className="font-sans text-xs text-[var(--color-text-muted)] font-medium">Vista previa en vivo</span>
          <div className="flex items-center gap-1 bg-[var(--color-background)] rounded-lg p-1 border border-[var(--color-border)]">
            {[['desktop', Monitor], ['mobile', Smartphone]].map(([m, Icon]) => (
              <button key={m} onClick={() => setPreviewMode(m)}
                className={cn('h-7 w-8 flex items-center justify-center rounded-md transition-all', previewMode === m ? 'bg-[var(--color-surface)] text-[var(--color-action)] shadow-sm' : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]')}>
                <Icon size={14} />
              </button>
            ))}
          </div>
        </div>

        {/* Preview area */}
        <div className={cn('flex-1 overflow-auto', previewMode === 'desktop' ? 'p-0' : 'py-6 px-6 bg-[var(--color-border)]')}>
          <div className={cn('h-full overflow-auto', previewMode === 'mobile' && 'max-w-[375px] mx-auto rounded-[2rem] shadow-2xl overflow-hidden border-4 border-[var(--color-border-strong)]')}>
            <StoreRenderer config={config} vendedorId={vendedorId} />
          </div>
        </div>
      </div>

      {showAddModal && <AddSectionModal onAdd={addSection} onClose={() => setShowAddModal(false)} />}
    </div>
  )
}
