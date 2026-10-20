import React, { useState, useEffect, useRef } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useQueries, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, PieChart, Pie, Cell, Legend,
} from 'recharts'
import {
  BarChart2, Package, History, Users, ShieldCheck, ShoppingBag, User,
  Plus, Edit, Trash2, FolderTree, X as XIcon, ImagePlus, Image as ImageIcon, Search,
  TrendingUp, FileSpreadsheet, ChevronDown, ChevronRight, ClipboardList, Store, Layers,
  Inbox, GitBranch, Star, AlertTriangle, CheckCircle, XCircle, RefreshCw,
} from 'lucide-react'
import { SyncHealthSection } from '../components/admin/SyncHealthSection'
import { toast } from 'sonner'
import { getCatalogStats, getAdminProducts, getProduct, getCategories, getCategorySchema, createProduct, updateProduct, deleteProduct } from '../api/products'
import { getAdminUsers, updateUserRoles, getAdminCategories, createCategory, updateCategorySchema, deleteCategory, uploadAdminImage, deletePendingAdminImage, getAdminVendors, getAdminSalesStats, getAdminSales, exportAdminSalesExcel, getAdminOrders, updateAdminOrderStatus, setVendorProfile, setTiendayaVendor, getProductOffers, getProductVariants, addProductVariant, updateProductVariant, deleteProductVariant, addProductOffer, updateProductOffer } from '../api/admin'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../components/ui/select'
import { Dialog, DialogContent, DialogTitle, DialogDescription, DialogClose } from '../components/ui/record-dialog'
import { Skeleton } from '../components/ui/skeleton'
import { Separator } from '../components/ui/separator'
import { formatQ, formatDate, cn } from '../lib/utils'
import { AdminCatalogRequestsSection } from '../components/admin/CatalogRequestsSection'
import { AdminVendorsSection } from './AdminVendorPage'
import { getAdminProductTrend, getAdminTrends } from '../api/analytics'
import ProductPicker from '../components/ProductPicker'
import { getFraudSummary, getFraudIndicator, getFraudAlertsPaginated, getFraudAnalysisStatus, recalculateFraudAlerts, updateFraudAlert, moderateReview } from '../api/reviews'

const NAV_ITEMS = [
  { id: 'stats',      label: 'Estadísticas', icon: BarChart2      },
  { id: 'analytics',  label: 'Tendencias',   icon: TrendingUp     },
  { id: 'products',   label: 'Productos',    icon: Package        },
  { id: 'categories', label: 'Categorías',   icon: FolderTree     },
  { id: 'users',      label: 'Usuarios',     icon: Users          },
  { id: 'vendors',    label: 'Vendedores',  icon: Store          },
  { id: 'orders',     label: 'Pedidos',      icon: ClipboardList  },
  { id: 'sales',      label: 'Ventas',       icon: TrendingUp     },
  { id: 'requests',   label: 'Solicitudes',  icon: Inbox          },
  { id: 'fraud',      label: 'Fraude & Reseñas', icon: AlertTriangle },
  { id: 'sync',       label: 'Salud de sincronización', icon: RefreshCw },
]

const ESTADO_BADGE = {
  pendiente:      'warning',
  confirmado:     'action',
  en_preparacion: 'action',
  enviado:        'jade',
  entregado:      'success',
  cancelado:      'error',
  reembolsado:    'default',
}

const ESTADO_LABEL = {
  pendiente:      'Pendiente',
  confirmado:     'Confirmado',
  preparando: 'En preparación', enviado_parcial: 'Envío parcial', entregado_parcial: 'Entrega parcial',
  en_preparacion: 'En preparación',
  enviado:        'Enviado',
  entregado:      'Entregado',
  cancelado:      'Cancelado',
  reembolsado:    'Reembolsado',
}

const ESTADO_CHART_COLORS = {
  pendiente:      '#f59e0b',
  confirmado:     '#3b82f6',
  en_preparacion: '#8b5cf6',
  enviado:        '#10b981',
  entregado:      '#16a34a',
  cancelado:      '#ef4444',
  reembolsado:    '#6b7280',
}

const ROLE_META = {
  administrador: { label: 'Admin',     Icon: ShieldCheck, active: 'bg-[var(--color-action)] text-white border-[var(--color-action)]',                      inactive: 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-action)] hover:text-[var(--color-action)]'       },
  vendedor:      { label: 'Vendedor',  Icon: ShoppingBag, active: 'bg-[var(--color-jade)] text-white border-[var(--color-jade)]',                            inactive: 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-jade)] hover:text-[var(--color-jade)]'             },
  comprador:     { label: 'Comprador', Icon: User,        active: 'bg-[var(--color-border-strong)] text-[var(--color-text-primary)] border-[var(--color-border-strong)]', inactive: 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-border-strong)] hover:text-[var(--color-text-primary)]' },
}
const ALL_ROLES = ['comprador', 'vendedor', 'administrador']

// ── AttrRow: FUERA de CategoriesSection para evitar remount en cada render ──
export function AttrRow({ attr, onChange, onRemove }) {
  return (
    <div className="grid grid-cols-[1fr_1fr_auto_auto_auto] gap-2 items-center">
      <Input
        placeholder="nombre (key)"
        value={attr.nombre}
        onChange={(e) => onChange({ ...attr, nombre: e.target.value.replace(/\s/g, '_') })}
        className="font-mono text-xs"
      />
      <Input
        placeholder="etiqueta (label)"
        value={attr.etiqueta}
        onChange={(e) => onChange({ ...attr, etiqueta: e.target.value })}
        className="text-xs"
      />
      <Select value={attr.tipo} onValueChange={(v) => onChange({ ...attr, tipo: v })}>
        <SelectTrigger className="w-28 text-xs"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="string">Texto</SelectItem>
          <SelectItem value="number">Número</SelectItem>
          <SelectItem value="boolean">Sí/No</SelectItem>
        </SelectContent>
      </Select>
      <label className="flex items-center gap-1 text-xs text-[var(--color-text-secondary)] whitespace-nowrap cursor-pointer">
        <input
          type="checkbox"
          checked={attr.requerido}
          onChange={(e) => onChange({ ...attr, requerido: e.target.checked })}
          className="h-3 w-3 accent-[var(--color-action)]"
        />
        Req.
      </label>
      <button
        type="button"
        onClick={onRemove}
        className="text-[var(--color-text-muted)] hover:text-[var(--color-error)] transition-colors"
      >
        <XIcon size={14} />
      </button>
    </div>
  )
}

// ── ImageManager: gestión de imágenes de un producto ──
function ImageManager({ images, onChange, onUploaded, onRemove }) {
  const fileRef = useRef(null)
  const [uploading, setUploading] = useState(false)

  async function handleFileChange(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const res = await uploadAdminImage(file)
      onChange([...images, res.data.url])
      onUploaded?.(res.data.url)
      toast.success('Imagen subida correctamente.')
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Error al subir la imagen.')
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  function remove(idx) {
    onRemove?.(images[idx])
    onChange(images.filter((_, i) => i !== idx))
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
          Imágenes del producto
        </p>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
        >
          <ImagePlus size={13} />
          {uploading ? 'Subiendo...' : 'Agregar imagen'}
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,image/gif"
          onChange={handleFileChange}
          className="hidden"
        />
      </div>

      {images.length === 0 ? (
        <div className="border border-dashed border-[var(--color-border)] rounded-[var(--radius-md)] py-6 text-center">
          <ImageIcon size={28} className="mx-auto mb-2 text-[var(--color-text-muted)]" strokeWidth={1} />
          <p className="font-sans text-xs text-[var(--color-text-muted)]">Sin imágenes todavía</p>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-2">
          {images.map((url, idx) => (
            <div key={idx} className="relative group aspect-square rounded-[var(--radius-md)] overflow-hidden border border-[var(--color-border)] bg-[var(--color-background)]">
              <img
                src={url}
                alt={`Imagen ${idx + 1}`}
                className="w-full h-full object-cover"
                onError={(e) => { e.target.style.display = 'none' }}
              />
              {idx === 0 && (
                <span className="absolute top-1 left-1 px-1.5 py-0.5 rounded text-[10px] font-sans font-semibold bg-[var(--color-action)] text-white">
                  Principal
                </span>
              )}
              <button
                type="button"
                onClick={() => remove(idx)}
                className="absolute top-1 right-1 h-6 w-6 rounded-full bg-black/60 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-[var(--color-error)]"
              >
                <XIcon size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
      {images.length > 0 && (
        <p className="font-sans text-[11px] text-[var(--color-text-muted)]">
          La primera imagen es la principal. Elimina y vuelve a subir para reordenar.
        </p>
      )}
    </div>
  )
}

// ── Helpers ──
function StatCard({ label, value, sub }) {
  return (
    <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5">
      <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-1">{label}</p>
      <p className="font-mono font-bold text-3xl text-[var(--color-text-primary)]">{value}</p>
      {sub && <p className="font-sans text-xs text-[var(--color-text-muted)] mt-1">{sub}</p>}
    </div>
  )
}

// ── StatsSection ──
function StatsSection() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['catalog-stats'],
    queryFn: () => getCatalogStats().then((r) => r.data[0]),
  })

  if (isLoading) return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}</div>
      <Skeleton className="h-64 w-full" />
    </div>
  )
  if (isError || !data) return <p className="font-sans text-sm text-[var(--color-error)]">Error al cargar estadísticas.</p>

  const global = data.resumen_global?.[0] || {}
  const porCategoria = data.estadisticas_por_categoria || []
  const topProductos = data.top_productos_precio || []

  const chartData = porCategoria.map((cat) => ({
    name: cat.categoria_nombre?.split(' ')[0] || cat._id,
    promedio: Math.round(cat.precio_promedio || 0),
  }))

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">
        <StatCard label="Total de productos" value={global.total_productos ?? '—'} />
        <StatCard label="Activos" value={global.total_activos ?? '—'} />
        <StatCard label="Inactivos" value={global.total_inactivos ?? '—'} />
        <StatCard label="Descontinuados" value={global.total_descontinuados ?? '—'} />
        <StatCard label="Disponibles" value={global.total_disponibles ?? '—'} sub="Activos con oferta e inventario" />
      </div>

      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5">
        <h3 className="font-display font-semibold text-base text-[var(--color-text-primary)] mb-4">Precio promedio por categoría</h3>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis dataKey="name" tick={{ fontSize: 11, fontFamily: 'var(--font-sans)', fill: 'var(--color-text-muted)' }} />
            <YAxis tick={{ fontSize: 11, fontFamily: 'var(--font-mono)', fill: 'var(--color-text-muted)' }} tickFormatter={(v) => `Q${v}`} />
            <Tooltip formatter={(v) => [formatQ(v), 'Precio promedio']} contentStyle={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', fontFamily: 'var(--font-sans)', fontSize: 12 }} />
            <Bar dataKey="promedio" fill="var(--color-action)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {topProductos.length > 0 && (
        <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
          <div className="px-5 py-4 border-b border-[var(--color-border)]">
            <h3 className="font-display font-semibold text-base text-[var(--color-text-primary)]">Top 5 productos más caros</h3>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[var(--color-background)]">
                {['Nombre', 'Categoría', 'Precio'].map((h) => (
                  <th key={h} className="px-5 py-3 text-left font-sans font-semibold text-xs uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)]">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {topProductos.slice(0, 5).map((prod, idx) => (
                <tr key={prod._id} className={idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]'}>
                  <td className="px-5 py-3 font-display font-semibold text-[var(--color-text-primary)]">{prod.nombre}</td>
                  <td className="px-5 py-3 font-sans text-[var(--color-text-secondary)]">{prod.categoria}</td>
                  <td className="px-5 py-3 font-mono font-bold text-[var(--color-text-primary)]">{formatQ(prod.precio)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {porCategoria.length > 0 && (
        <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
          <div className="px-5 py-4 border-b border-[var(--color-border)]">
            <h3 className="font-display font-semibold text-base text-[var(--color-text-primary)]">Estadísticas por categoría</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-[var(--color-background)]">
                  {['Categoría', 'Total', 'Disponibles', 'Precio mín', 'Precio máx', 'Promedio'].map((h) => (
                    <th key={h} className="px-4 py-3 text-left font-sans font-semibold text-xs uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)] whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {porCategoria.map((cat, idx) => (
                  <tr key={cat._id} className={idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]'}>
                    <td className="px-4 py-3 font-display font-semibold text-[var(--color-text-primary)]">{cat.categoria_nombre}</td>
                    <td className="px-4 py-3 font-mono text-[var(--color-text-primary)]">{cat.total_productos}</td>
                    <td className="px-4 py-3 font-mono text-[var(--color-text-primary)]">{cat.disponibles}</td>
                    <td className="px-4 py-3 font-mono text-[var(--color-text-primary)]">{formatQ(cat.precio_minimo)}</td>
                    <td className="px-4 py-3 font-mono text-[var(--color-text-primary)]">{formatQ(cat.precio_maximo)}</td>
                    <td className="px-4 py-3 font-mono font-semibold text-[var(--color-text-primary)]">{formatQ(cat.precio_promedio)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

// ── ProductFormModal ──
export function ProductFormModal({ open, onOpenChange, product, onDuplicateFound }) {
  const isEdit = !!product
  const queryClient = useQueryClient()

  const EMPTY = { nombre: '', descripcion: '', precio: '', categoria_slugs: [], disponible: true, estado: 'activo', atributos: {}, stock: '', imagenes: [], vendedor_usuario_id: '' }
  const [form, setForm] = useState(EMPTY)
  const [stagedImages, setStagedImages] = useState([])

  useEffect(() => {
    if (open) {
      setStagedImages([])
      if (isEdit) {
        // Extraer URLs de imágenes (formato MongoDB: [{url, orden}] → [url])
        const imgs = (product.imagenes || []).map(img =>
          typeof img === 'string' ? img : img?.url
        ).filter(Boolean)
        setForm({
          nombre: product.nombre || '',
          descripcion: product.descripcion || '',
          precio: String(product.precio || ''),
          categoria_slugs: product.categorias?.map(c => c.slug) || (product.categoria?.slug ? [product.categoria.slug] : []),
          disponible: product.disponible ?? true,
          estado: product.estado || 'activo',
          atributos: { ...(product.atributos || {}) },
          stock: product.stock ?? '',
          imagenes: imgs,
          vendedor_usuario_id: product.vendedor_usuario_id || '',
        })
      } else {
        setForm(EMPTY)
      }
    }
  }, [open, product])

  const { data: categoriesData } = useQuery({
    queryKey: ['categories'],
    queryFn: () => getCategories().then((r) => r.data),
  })
  const categories = categoriesData || []

  const { data: vendorsData } = useQuery({
    queryKey: ['admin-vendors'],
    queryFn: () => getAdminVendors().then((r) => r.data),
    staleTime: 2 * 60 * 1000,
  })
  const vendors = vendorsData || []

  const mutation = useMutation({
    mutationFn: (payload) => isEdit ? updateProduct(product._id, payload) : createProduct(payload),
    onSuccess: () => {
      toast.success(isEdit ? 'Producto actualizado.' : 'Producto creado.')
      queryClient.invalidateQueries({ queryKey: ['admin-products'] })
      queryClient.invalidateQueries({ queryKey: ['products'] })
      setStagedImages([])
      onOpenChange(false)
    },
    onError: (err) => {
      const detail = err?.response?.data?.detail
      if (err?.response?.status === 409 && detail?.existing_id) {
        toast.error(`Ya existe: "${detail.existing_nombre}". ¿Quieres editarlo?`, {
          action: {
            label: 'Ir a editar',
            onClick: () => {
              onOpenChange(false)
              onDuplicateFound?.(detail.existing_id)
            },
          },
        })
        return
      }
      toast.error(typeof detail === 'string' ? detail : 'Error al guardar el producto.')
    },
  })

  function set(key, value) { setForm((p) => ({ ...p, [key]: value })) }
  function setAttr(key, value) { setForm((p) => ({ ...p, atributos: { ...p.atributos, [key]: value } })) }

  function imageIdFromUrl(url) {
    const match = /^\/api\/v1\/products\/images\/(\d+)$/.exec(url || '')
    return match ? Number(match[1]) : null
  }

  function discardStagedImage(url) {
    if (!stagedImages.includes(url)) return
    setStagedImages((current) => current.filter((item) => item !== url))
    const imageId = imageIdFromUrl(url)
    if (imageId) deletePendingAdminImage(imageId).catch(() => {})
  }

  function handleDialogOpenChange(nextOpen) {
    if (!nextOpen && stagedImages.length) {
      stagedImages.forEach((url) => {
        const imageId = imageIdFromUrl(url)
        if (imageId) deletePendingAdminImage(imageId).catch(() => {})
      })
      setStagedImages([])
    }
    onOpenChange(nextOpen)
  }

  const schemasQueries = useQueries({
    queries: form.categoria_slugs.map((slug) => ({
      queryKey: ['category-schema', slug],
      queryFn: () => getCategorySchema(slug).then((r) => r.data),
      enabled: !!slug,
      staleTime: 5 * 60 * 1000,
    })),
  })

  const allAttrSections = form.categoria_slugs.map((slug, idx) => {
    const cat = categories.find((c) => c.slug === slug)
    return {
      slug,
      catNombre: cat?.nombre || slug,
      fields: schemasQueries[idx]?.data?.atributos || [],
    }
  }).filter((s) => s.fields.length > 0)

  function handleSubmit(e) {
    e.preventDefault()
    if (!form.nombre || !form.precio) return toast.error('Nombre y precio son obligatorios.')
    if (form.categoria_slugs.length === 0) return toast.error('Selecciona al menos una categoría.')
    if (!isEdit && form.vendedor_usuario_id === '') return toast.error('Selecciona el vendedor de la oferta inicial.')
    const missingAttributes = allAttrSections.flatMap(({ fields }) => fields)
      .filter(({ nombre, requerido }) => requerido && (
        form.atributos[nombre] === undefined
        || form.atributos[nombre] === null
        || form.atributos[nombre] === ''
      ))
    if (missingAttributes.length > 0) {
      return toast.error(`Completa: ${missingAttributes.map(field => field.etiqueta).join(', ')}.`)
    }

    const atributos = {}
    allAttrSections.forEach(({ fields }) => {
      fields.forEach(({ nombre, tipo }) => {
        const v = form.atributos[nombre]
        if (v === '' || v === undefined || v === null) return
        atributos[nombre] = tipo === 'number' ? Number(v) : v
      })
    })

    const payload = isEdit
      ? {
          nombre: form.nombre,
          descripcion: form.descripcion,
          precio: Number(form.precio),
          disponible: form.disponible,
          estado: form.estado,
          atributos,
          imagenes: form.imagenes,
          categoria_slugs: form.categoria_slugs,
          ...(form.stock !== '' && { stock: Number(form.stock) }),
          ...(form.vendedor_usuario_id !== '' && { vendedor_usuario_id: Number(form.vendedor_usuario_id) }),
        }
      : {
          nombre: form.nombre,
          descripcion: form.descripcion,
          precio: Number(form.precio),
          categoria_slugs: form.categoria_slugs,
          atributos,
          imagenes: form.imagenes,
          stock: Number(form.stock) || 0,
          ...(form.vendedor_usuario_id !== '' && { vendedor_usuario_id: Number(form.vendedor_usuario_id) }),
        }

    mutation.mutate(payload)
  }

  return (
    <Dialog open={open} onOpenChange={handleDialogOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogTitle>{isEdit ? 'Editar producto' : 'Nuevo producto'}</DialogTitle>
        <DialogDescription>{isEdit ? `SKU: ${product?.sku}` : 'Los campos con * son obligatorios.'}</DialogDescription>

        <form onSubmit={handleSubmit} className="space-y-4 mt-2">
          <div>
            <Label>Nombre *</Label>
            <Input value={form.nombre} onChange={(e) => set('nombre', e.target.value)} placeholder="Laptop ASUS..." />
          </div>

          {/* Categorías — visible en crear y editar */}
          <div>
            <Label>Categorías * <span className="text-[var(--color-text-muted)] font-normal text-xs">(la primera es la principal)</span></Label>
            <div className="flex flex-wrap gap-1.5 mt-1.5 mb-2 min-h-[26px]">
              {form.categoria_slugs.map((slug, idx) => {
                const cat = categories.find(c => c.slug === slug)
                return (
                  <span key={slug} className="inline-flex items-center gap-1 pl-2 pr-1 py-0.5 rounded-full text-xs font-sans font-semibold bg-[var(--color-action)]/10 text-[var(--color-action)] border border-[var(--color-action)]/30">
                    {idx === 0 && <span className="text-[9px] uppercase opacity-50 mr-0.5">Principal ·</span>}
                    {cat?.nombre || slug}
                    <button type="button" onClick={() => set('categoria_slugs', form.categoria_slugs.filter(s => s !== slug))} className="ml-0.5 rounded-full hover:bg-[var(--color-action)]/20 p-0.5">
                      <XIcon size={10} />
                    </button>
                  </span>
                )
              })}
            </div>
            <Select
              value=""
              onValueChange={(v) => {
                if (!form.categoria_slugs.includes(v)) {
                  const isFirst = form.categoria_slugs.length === 0
                  set('categoria_slugs', [...form.categoria_slugs, v])
                  if (isFirst) set('atributos', {})
                }
              }}
            >
              <SelectTrigger><SelectValue placeholder="Añadir categoría..." /></SelectTrigger>
              <SelectContent>
                {categories.filter(c => !form.categoria_slugs.includes(c.slug)).map(c => (
                  <SelectItem key={c.slug} value={c.slug}>{c.nombre}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Precio (GTQ) *</Label>
              <Input type="number" step="0.01" min="0" value={form.precio} onChange={(e) => set('precio', e.target.value)} placeholder="999.99" />
            </div>
            {isEdit && (
              <div>
                <Label>Estado</Label>
                <Select value={form.estado} onValueChange={(v) => set('estado', v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="activo">Activo</SelectItem>
                    <SelectItem value="inactivo">Inactivo</SelectItem>
                    <SelectItem value="descontinuado">Descontinuado</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Stock (unidades)</Label>
              <Input type="number" min="0" step="1" value={form.stock} onChange={(e) => set('stock', e.target.value)} placeholder="0" />
            </div>
            <div>
              <Label>Vendedor asignado</Label>
              <Select value={form.vendedor_usuario_id || '__none__'} onValueChange={(v) => set('vendedor_usuario_id', v === '__none__' ? '' : v)}>
                <SelectTrigger><SelectValue placeholder="Sin asignar" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Sin asignar</SelectItem>
                  {vendors.map((v) => (
                    <SelectItem key={v.usuario_id} value={String(v.usuario_id)}>
                      {v.nombre_comercial ? `${v.nombre_comercial} (${v.nombre_completo})` : v.nombre_completo}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div>
            <Label>Descripción</Label>
            <textarea
              value={form.descripcion || ''}
              onChange={(e) => set('descripcion', e.target.value)}
              rows={2}
              placeholder="Descripción del producto..."
              className="w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm font-sans text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-action)] resize-none"
            />
          </div>

          {isEdit && (
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.disponible} onChange={(e) => set('disponible', e.target.checked)} className="h-4 w-4 accent-[var(--color-action)]" />
              <span className="font-sans text-sm text-[var(--color-text-primary)]">Disponible (en stock)</span>
            </label>
          )}

          <Separator />

          {/* Imágenes */}
          <ImageManager
            images={form.imagenes}
            onChange={(imgs) => set('imagenes', imgs)}
            onUploaded={(url) => setStagedImages((current) => [...current, url])}
            onRemove={discardStagedImage}
          />

          {allAttrSections.map(({ slug, catNombre, fields }) => (
            <React.Fragment key={slug}>
              <Separator />
              <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                Atributos de {catNombre}
              </p>
              <div className="grid grid-cols-2 gap-3">
                {fields.map((field) => (
                  <div key={field.nombre} className={field.tipo === 'boolean' ? 'flex items-center gap-2 col-span-1' : ''}>
                    {field.tipo === 'boolean' ? (
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" checked={!!form.atributos[field.nombre]} onChange={(e) => setAttr(field.nombre, e.target.checked)} className="h-4 w-4 accent-[var(--color-action)]" />
                        <span className="font-sans text-sm text-[var(--color-text-primary)]">{field.etiqueta}{field.requerido ? ' *' : ''}</span>
                      </label>
                    ) : (
                      <>
                        <Label>{field.etiqueta}{field.requerido ? ' *' : ''}</Label>
                        <Input
                          type={field.tipo === 'number' ? 'number' : 'text'}
                          step={field.tipo === 'number' ? 'any' : undefined}
                          placeholder={field.placeholder || ''}
                          value={form.atributos[field.nombre] ?? ''}
                          onChange={(e) => setAttr(field.nombre, e.target.value)}
                        />
                      </>
                    )}
                  </div>
                ))}
              </div>
            </React.Fragment>
          ))}

          <div className="flex justify-end gap-2 pt-2">
            <DialogClose asChild>
              <Button type="button" variant="secondary">Cancelar</Button>
            </DialogClose>
            <Button type="submit" loading={mutation.isPending}>
              {isEdit ? 'Guardar cambios' : 'Crear producto'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function currentMonday() {
  const now = new Date()
  const day = (now.getDay() + 6) % 7
  now.setDate(now.getDate() - day)
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

function shiftWeek(week, amount) {
  const value = new Date(`${week}T12:00:00`)
  value.setDate(value.getDate() + amount * 7)
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
}

const loadAdminAnalyticsProducts = (params) => getAdminProducts({ ...params, estado: 'todos' })
const ANALYTICS_COLORS = ['var(--color-action)', 'var(--color-jade)', '#f59e0b', '#8b5cf6', '#64748b']

function AnalyticsSection() {
  const [week, setWeek] = useState(currentMonday)
  const [comparisonWeeks, setComparisonWeeks] = useState(1)
  const [onlyWithoutSales, setOnlyWithoutSales] = useState(false)
  const [selectedProduct, setSelectedProduct] = useState(null)
  const [fromWeek, setFromWeek] = useState(() => shiftWeek(currentMonday(), -11))
  const [toWeek, setToWeek] = useState(currentMonday)
  const productRef = selectedProduct?._id || ''
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['cassandra-trends', week, comparisonWeeks, onlyWithoutSales],
    queryFn: () => getAdminTrends(week, comparisonWeeks, onlyWithoutSales).then(r => r.data),
    retry: false,
  })
  const { data: productTrend, isLoading: productTrendLoading, isError: productTrendError, error: productTrendRequestError } = useQuery({
    queryKey: ['cassandra-product-trend', productRef, fromWeek, toWeek],
    queryFn: () => getAdminProductTrend(productRef, fromWeek, toWeek).then(r => r.data),
    enabled: !!productRef && !!fromWeek && !!toWeek && fromWeek <= toWeek,
    retry: false,
  })
  const rows = data?.items || []
  const productRows = productTrend?.items || []
  const comparedWeeks = rows[0]?.semanas?.map(item => item.semana_inicio) || []
  const chart = rows.slice(0, 10).map(item => ({
    nombre: item.producto_nombre?.slice(0, 24),
    ...Object.fromEntries((item.semanas || []).map(value => [value.semana_inicio, value.unidades])),
  }))
  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="font-display font-semibold text-lg">Demanda por semana</h3>
          <p className="font-sans text-sm text-[var(--color-text-secondary)]">Ventas pagadas de lunes a domingo.</p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="font-sans text-xs text-[var(--color-text-secondary)]">Semanas anteriores
            <Select value={String(comparisonWeeks)} onValueChange={value => setComparisonWeeks(Number(value))}>
              <SelectTrigger className="mt-1 w-44"><SelectValue /></SelectTrigger>
              <SelectContent>{[0,1,2,3,4].map(value => <SelectItem key={value} value={String(value)}>{value === 0 ? 'Solo la actual' : `${value} anterior${value > 1 ? 'es' : ''}`}</SelectItem>)}</SelectContent>
            </Select>
          </label>
          <label className="font-sans text-xs text-[var(--color-text-secondary)]">Semana que inicia
            <Input type="date" min="2020-01-06" step="7" value={week} onChange={e => setWeek(e.target.value)} className="mt-1" />
          </label>
        </div>
      </div>
      <div className="flex gap-2">
        <Button variant={!onlyWithoutSales ? 'primary' : 'secondary'} onClick={() => setOnlyWithoutSales(false)}>Con actividad</Button>
        <Button variant={onlyWithoutSales ? 'primary' : 'secondary'} onClick={() => setOnlyWithoutSales(true)}>Sin ventas</Button>
      </div>
      {isLoading ? <Skeleton className="h-72 w-full" /> : isError ? (
        <p role="alert" className="text-sm text-[var(--color-error)]">{error?.response?.data?.detail || 'No se pudo consultar Cassandra.'}</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-[var(--color-text-muted)] py-10 text-center">{onlyWithoutSales ? 'Todos los productos registraron ventas esta semana.' : 'No hay ventas pagadas en el período seleccionado.'}</p>
      ) : onlyWithoutSales ? (
        <div className="overflow-x-auto border border-[var(--color-border)] rounded-[var(--radius-lg)]">
          <table className="w-full text-sm"><thead><tr className="bg-[var(--color-background)]">
            {['Producto','SKU','Categorías','Estado','Resultado'].map(header => <th key={header} className="px-4 py-3 text-left text-xs uppercase text-[var(--color-text-muted)]">{header}</th>)}
          </tr></thead><tbody>{rows.map(item => <tr key={item.producto_ref} className="border-t border-[var(--color-border)] bg-red-50">
            <td className="px-4 py-3 font-semibold">{item.producto_nombre}</td><td className="px-4 py-3 font-mono">{item.sku || '—'}</td>
            <td className="px-4 py-3">{item.categorias?.join(', ') || 'Sin categoría'}</td><td className="px-4 py-3 capitalize">{item.estado || '—'}</td>
            <td className="px-4 py-3 font-semibold text-[var(--color-error)]">0 · Sin ventas</td>
          </tr>)}</tbody></table>
        </div>
      ) : <>
        <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5">
          <h4 className="font-display font-semibold mb-4">Top productos — semana actual y comparaciones</h4>
          <ResponsiveContainer width="100%" height={300}><BarChart data={chart} margin={{ left: 4, right: 12 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" /><XAxis dataKey="nombre" tick={{ fontSize: 10 }} interval={0} angle={-15} textAnchor="end" height={70} /><YAxis allowDecimals={false} /><Tooltip /><Legend />
            {comparedWeeks.map((value, index) => <Bar key={value} dataKey={value} name={index === 0 ? `Actual · ${value}` : `${index} sem. antes · ${value}`} fill={ANALYTICS_COLORS[index]} radius={[4,4,0,0]} />)}
          </BarChart></ResponsiveContainer>
        </div>
        <div className="overflow-x-auto border border-[var(--color-border)] rounded-[var(--radius-lg)]"><table className="w-full text-sm">
          <thead><tr className="bg-[var(--color-background)]"><th className="px-4 py-3 text-left text-xs uppercase text-[var(--color-text-muted)]">Producto</th>
            {comparedWeeks.map((value, index) => <th key={value} className="px-4 py-3 text-left text-xs uppercase text-[var(--color-text-muted)]">{index === 0 ? 'Actual' : `Hace ${index} sem.`}</th>)}
            {comparisonWeeks > 0 && <th className="px-4 py-3 text-left text-xs uppercase text-[var(--color-text-muted)]">Variación</th>}
            {['Ingresos netos','Ofertas','Flash'].map(header => <th key={header} className="px-4 py-3 text-left text-xs uppercase text-[var(--color-text-muted)]">{header}</th>)}
          </tr></thead><tbody>{rows.map(item => <tr key={item.producto_ref} className={cn('border-t border-[var(--color-border)]', item.unidades === 0 && 'bg-red-50')}>
            <td className="px-4 py-3 font-semibold">{item.producto_nombre}</td>
            {(item.semanas || []).map(value => <td key={value.semana_inicio} className={cn('px-4 py-3 font-mono', value.unidades === 0 && 'text-[var(--color-error)]')}>{value.unidades}</td>)}
            {comparisonWeeks > 0 && <td className={cn('px-4 py-3 font-mono font-semibold', item.variacion_unidades >= 0 ? 'text-[var(--color-success)]' : 'text-[var(--color-error)]')}>{item.variacion_unidades >= 0 ? '+' : ''}{item.variacion_unidades}</td>}
            <td className="px-4 py-3 font-mono">{formatQ(item.ingresos_netos)}</td><td className="px-4 py-3 font-mono">{item.ofertas}</td><td className="px-4 py-3 font-mono">{item.unidades_flash}</td>
          </tr>)}</tbody>
        </table></div>
      </>}

      <div className="border-t border-[var(--color-border)] pt-6 space-y-5">
        <div><h3 className="font-display font-semibold text-lg">Seguimiento semanal por producto</h3><p className="font-sans text-sm text-[var(--color-text-secondary)]">Busca visualmente un producto y consulta su serie continua; las semanas sin ventas aparecen en cero.</p></div>
        <ProductPicker value={selectedProduct} onSelect={setSelectedProduct} loadProducts={loadAdminAnalyticsProducts} queryKey="admin-analytics-product-picker" title="Producto para seguimiento" description="Busca por nombre o SKU y selecciona el producto por su imagen." />
        <div className="grid gap-3 sm:grid-cols-2 max-w-xl">
          <label className="font-sans text-xs text-[var(--color-text-secondary)]">Desde (lunes)<Input type="date" min="2020-01-06" step="7" value={fromWeek} onChange={event => setFromWeek(event.target.value)} className="mt-1" /></label>
          <label className="font-sans text-xs text-[var(--color-text-secondary)]">Hasta (lunes)<Input type="date" min="2020-01-06" step="7" value={toWeek} onChange={event => setToWeek(event.target.value)} className="mt-1" /></label>
        </div>
        {fromWeek > toWeek ? <p role="alert" className="text-sm text-[var(--color-error)]">La semana inicial no puede ser posterior a la final.</p> : !productRef ? <p className="text-sm text-[var(--color-text-muted)] py-8 text-center">Selecciona un producto para consultar su evolución.</p> : productTrendLoading ? <Skeleton className="h-72 w-full" /> : productTrendError ? <p role="alert" className="text-sm text-[var(--color-error)]">{productTrendRequestError?.response?.data?.detail || 'No se pudo consultar el seguimiento del producto.'}</p> : <>
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5"><h4 className="font-display font-semibold mb-4">{productTrend?.producto_nombre}</h4><ResponsiveContainer width="100%" height={280}><LineChart data={productRows} margin={{ left: 4, right: 12 }}><CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" /><XAxis dataKey="semana_inicio" tick={{ fontSize: 11 }} /><YAxis allowDecimals={false} /><Tooltip /><Line type="monotone" dataKey="unidades" name="Unidades vendidas" stroke="var(--color-action)" strokeWidth={3} dot={{ r: 4 }} /></LineChart></ResponsiveContainer></div>
          <div className="overflow-x-auto border border-[var(--color-border)] rounded-[var(--radius-lg)]"><table className="w-full text-sm"><thead><tr className="bg-[var(--color-background)]">{['Semana','Unidades','Variación','Ingresos netos','Pedidos','Ofertas','Flash'].map(header => <th key={header} className="px-4 py-3 text-left text-xs uppercase text-[var(--color-text-muted)]">{header}</th>)}</tr></thead><tbody>{productRows.map(item => <tr key={item.semana_inicio} className={cn('border-t border-[var(--color-border)]', item.unidades === 0 && 'bg-red-50')}><td className="px-4 py-3 font-semibold">{item.semana_inicio}</td><td className={cn('px-4 py-3 font-mono font-semibold', item.unidades === 0 && 'text-[var(--color-error)]')}>{item.unidades === 0 ? '0 · Sin ventas' : item.unidades}</td><td className={cn('px-4 py-3 font-mono font-semibold', item.variacion_unidades >= 0 ? 'text-[var(--color-success)]' : 'text-[var(--color-error)]')}>{item.variacion_unidades >= 0 ? '+' : ''}{item.variacion_unidades}</td><td className="px-4 py-3 font-mono">{formatQ(item.ingresos_netos)}</td><td className="px-4 py-3 font-mono">{item.pedidos}</td><td className="px-4 py-3 font-mono">{item.ofertas}</td><td className="px-4 py-3 font-mono">{item.unidades_flash}</td></tr>)}</tbody></table></div>
        </>}
      </div>
    </section>
  )
}

// ── ProductsSection ──
// ── VariantsModal ──
export function VariantsModal({ product, open, onOpenChange }) {
  const queryClient = useQueryClient()
  const [variantAttrs, setVariantAttrs] = useState([{ id: 1, key: '', value: '' }])
  const [nextId, setNextId] = useState(2)
  const [editingVariantId, setEditingVariantId] = useState(null)
  const [editAttrs, setEditAttrs] = useState([])

  const { data: variants = [], isLoading } = useQuery({
    queryKey: ['product-variants', product?._id],
    queryFn: () => getProductVariants(product._id).then(r => r.data),
    enabled: open && !!product,
  })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['product-variants', product?._id] })
    queryClient.invalidateQueries({ queryKey: ['product-offers', product?._id] })
    queryClient.invalidateQueries({ queryKey: ['admin-products'] })
    queryClient.invalidateQueries({ queryKey: ['products'] })
  }

  const createMutation = useMutation({
    mutationFn: (data) => addProductVariant(product._id, data),
    onSuccess: () => {
      toast.success('Variante creada.')
      setVariantAttrs([{ id: 1, key: '', value: '' }])
      setNextId(2)
      invalidate()
    },
    onError: (err) => toast.error(err?.response?.data?.detail || 'No se pudo crear la variante.'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ varianteId, data }) => updateProductVariant(varianteId, data),
    onSuccess: () => {
      toast.success('Variante actualizada.')
      setEditingVariantId(null)
      invalidate()
    },
    onError: (err) => toast.error(err?.response?.data?.detail || 'Error al actualizar variante.'),
  })

  const deleteMutation = useMutation({
    mutationFn: (varianteId) => deleteProductVariant(varianteId),
    onSuccess: () => { toast.success('Variante eliminada.'); invalidate() },
    onError: (err) => toast.error(err?.response?.data?.detail || 'No se pudo eliminar la variante.'),
  })

  function handleCreate() {
    const atributos = Object.fromEntries(
      variantAttrs.filter(r => r.key.trim() && r.value.trim()).map(r => [r.key.trim(), r.value.trim()])
    )
    if (!Object.keys(atributos).length) return toast.error('Agrega al menos un atributo.')
    createMutation.mutate({ atributos })
  }

  function startEdit(v) {
    setEditingVariantId(v.variante_id)
    setEditAttrs(Object.entries(v.atributos || {}).map(([k, val]) => ({ id: k, key: k, value: String(val) })))
  }

  function handleSave(v) {
    const atributos = Object.fromEntries(
      editAttrs.filter(r => r.key.trim() && r.value.trim()).map(r => [r.key.trim(), r.value.trim()])
    )
    if (!Object.keys(atributos).length) return toast.error('Agrega al menos un atributo.')
    updateMutation.mutate({ varianteId: v.variante_id, data: { atributos } })
  }

  function handleDelete(v) {
    const label = Object.entries(v.atributos || {}).map(([k, val]) => `${k}: ${val}`).join(', ') || 'Predeterminada'
    if (!window.confirm(`¿Eliminar la variante "${label}"? Solo es posible si no tiene ofertas activas.`)) return
    deleteMutation.mutate(v.variante_id)
  }

  function addEditRow() {
    setEditAttrs(rows => [...rows, { id: Date.now(), key: '', value: '' }])
  }

  function addCreateRow() {
    setVariantAttrs(rows => [...rows, { id: nextId, key: '', value: '' }])
    setNextId(n => n + 1)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogTitle className="flex items-center gap-2">
          <GitBranch size={16} /> Variantes — {product?.nombre}
        </DialogTitle>
        <DialogDescription>
          Cada variante es una combinación única de atributos (ej. color + talla). Los vendedores crean ofertas por variante.
        </DialogDescription>

        {/* Lista de variantes */}
        <div className="space-y-1.5">
          <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
            Variantes registradas
          </p>
          {isLoading ? (
            <div className="space-y-2">{[1, 2, 3].map(i => <Skeleton key={i} className="h-10 w-full" />)}</div>
          ) : variants.length === 0 ? (
            <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] px-4 py-6 text-center font-sans text-sm text-[var(--color-text-muted)]">
              Sin variantes. Crea la primera abajo.
            </div>
          ) : (
            <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[520px]">
                  <thead>
                    <tr className="bg-[var(--color-background)] border-b border-[var(--color-border)]">
                      {['Atributos', 'SKU catálogo', 'Estado', ''].map(h => (
                        <th key={h} className="px-3 py-2 text-left font-sans font-semibold text-xs uppercase tracking-wider text-[var(--color-text-muted)] whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {variants.map(v => (
                      <tr key={v.variante_id} className="border-b border-[var(--color-border)] last:border-0 hover:bg-[var(--color-background)] transition-colors">
                        <td className="px-3 py-2.5">
                          {editingVariantId === v.variante_id ? (
                            <div className="space-y-1.5">
                              {editAttrs.map((row, i) => (
                                <div key={row.id} className="grid grid-cols-[1fr_1fr_auto] gap-1.5">
                                  <Input placeholder="Atributo" value={row.key} onChange={e => setEditAttrs(rows => rows.map((r, ri) => ri === i ? { ...r, key: e.target.value } : r))} className="h-7 text-xs" />
                                  <Input placeholder="Valor" value={row.value} onChange={e => setEditAttrs(rows => rows.map((r, ri) => ri === i ? { ...r, value: e.target.value } : r))} className="h-7 text-xs" />
                                  <Button type="button" variant="ghost" size="icon-sm" onClick={() => setEditAttrs(rows => rows.filter((_, ri) => ri !== i))}><XIcon size={11} /></Button>
                                </div>
                              ))}
                              <Button type="button" size="sm" variant="secondary" onClick={addEditRow} className="mt-1"><Plus size={11} /> Atributo</Button>
                            </div>
                          ) : (
                            <span className="inline-flex flex-wrap gap-1">
                              {Object.entries(v.atributos || {}).length ? (
                                Object.entries(v.atributos).map(([k, val]) => (
                                  <span key={k} className="inline-block rounded bg-[var(--color-border)] px-1.5 py-0.5 text-[11px] font-sans text-[var(--color-text-secondary)]">
                                    {k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}: {val}
                                  </span>
                                ))
                              ) : (
                                <span className="text-xs text-[var(--color-text-muted)] italic">Predeterminada</span>
                              )}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-xs text-[var(--color-text-muted)] whitespace-nowrap">{v.sku_catalogo}</td>
                        <td className="px-3 py-2.5 whitespace-nowrap">
                          <div className="flex items-center gap-1">
                            <Badge variant={v.estado === 'activa' ? 'success' : 'secondary'}>{v.estado}</Badge>
                            {v.es_predeterminada && <Badge variant="action">Default</Badge>}
                          </div>
                        </td>
                        <td className="px-3 py-2.5 whitespace-nowrap">
                          <div className="flex items-center gap-1">
                            {editingVariantId === v.variante_id ? (
                              <>
                                <Button size="sm" variant="ghost" onClick={() => handleSave(v)} disabled={updateMutation.isPending}>Guardar</Button>
                                <Button size="sm" variant="ghost" onClick={() => setEditingVariantId(null)}>Cancelar</Button>
                              </>
                            ) : (
                              <>
                                <Button size="sm" variant="ghost" onClick={() => startEdit(v)} title="Editar atributos"><Edit size={12} /></Button>
                                <Button size="sm" variant="ghost" className="text-[var(--color-error)] hover:text-[var(--color-error)] hover:bg-[var(--color-error)]/10" onClick={() => handleDelete(v)} disabled={deleteMutation.isPending} title="Eliminar variante">
                                  <Trash2 size={12} />
                                </Button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Crear variante */}
        <div className="border border-[var(--color-border)] rounded-[var(--radius-md)] p-4 space-y-3">
          <div>
            <p className="font-sans text-sm font-semibold text-[var(--color-text-primary)]">Nueva variante</p>
            <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
              Define los atributos que la distinguen (ej. color + talla). Cada combinación genera un SKU único.
            </p>
          </div>
          <div className="space-y-2">
            {variantAttrs.map((row, index) => (
              <div key={row.id} className="grid grid-cols-[1fr_1fr_auto] gap-2">
                <Input placeholder="Atributo (ej. color)" value={row.key} onChange={e => setVariantAttrs(rows => rows.map((r, i) => i === index ? { ...r, key: e.target.value } : r))} />
                <Input placeholder="Valor (ej. azul)" value={row.value} onChange={e => setVariantAttrs(rows => rows.map((r, i) => i === index ? { ...r, value: e.target.value } : r))} />
                <Button type="button" variant="ghost" size="icon-sm" onClick={() => setVariantAttrs(rows => rows.filter((_, i) => i !== index))}><XIcon size={13} /></Button>
              </div>
            ))}
          </div>
          <div className="flex justify-between">
            <Button type="button" size="sm" variant="secondary" onClick={addCreateRow}><Plus size={13} /> Atributo</Button>
            <Button type="button" size="sm" onClick={handleCreate} loading={createMutation.isPending}>Crear variante</Button>
          </div>
        </div>

        <div className="flex justify-end pt-1">
          <DialogClose asChild><Button variant="secondary" size="sm">Cerrar</Button></DialogClose>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ── OffersModal ──
export function OffersModal({ product, open, onOpenChange }) {
  const queryClient = useQueryClient()
  const [newVendorId, setNewVendorId] = useState('')
  const [newVariantId, setNewVariantId] = useState('')
  const [newPrecio, setNewPrecio] = useState('')
  const [newStock, setNewStock] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [editPrecio, setEditPrecio] = useState('')
  const [editStock, setEditStock] = useState('')

  const { data: offers = [], isLoading } = useQuery({
    queryKey: ['product-offers', product?._id],
    queryFn: () => getProductOffers(product._id).then((r) => r.data),
    enabled: open && !!product,
  })

  const { data: variants = [] } = useQuery({
    queryKey: ['product-variants', product?._id],
    queryFn: () => getProductVariants(product._id).then((r) => r.data),
    enabled: open && !!product,
  })

  const { data: vendorsData = [] } = useQuery({
    queryKey: ['admin-vendors'],
    queryFn: () => getAdminVendors().then((r) => r.data),
    enabled: open,
  })

  const selectedVariant = newVariantId || String(variants[0]?.variante_id || '')
  const existingVendorIds = new Set(offers.filter(
    o => o.estado !== 'descontinuada' && String(o.producto_variante_id) === selectedVariant
  ).map(o => o.vendedor_id))
  const availableVendors = vendorsData.filter(
    v => v.vendedor_id && !existingVendorIds.has(v.vendedor_id)
  )

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['product-offers', product?._id] })
    queryClient.invalidateQueries({ queryKey: ['product-variants', product?._id] })
    queryClient.invalidateQueries({ queryKey: ['admin-products'] })
    queryClient.invalidateQueries({ queryKey: ['products'] })
  }

  const addMutation = useMutation({
    mutationFn: (data) => addProductOffer(product._id, data),
    onSuccess: () => {
      toast.success('Oferta añadida.')
      setNewVendorId(''); setNewPrecio(''); setNewStock('')
      invalidate()
    },
    onError: (err) => toast.error(err?.response?.data?.detail || 'Error al añadir oferta.'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ ofertaId, data }) => updateProductOffer(ofertaId, data),
    onSuccess: () => {
      toast.success('Oferta actualizada.')
      setEditingId(null)
      invalidate()
    },
    onError: (err) => toast.error(err?.response?.data?.detail || 'Error al actualizar.'),
  })

  function handleAdd(e) {
    e.preventDefault()
    if (!newVendorId) return
    addMutation.mutate({ vendedor_id: Number(newVendorId), producto_variante_id: Number(selectedVariant), precio: Number(newPrecio), stock: Number(newStock) })
  }

  function startEdit(offer) {
    setEditingId(offer.oferta_id)
    setEditPrecio(String(offer.precio))
    setEditStock(String(offer.stock_disponible ?? offer.stock))
  }

  function handleSaveEdit(offer) {
    updateMutation.mutate({ ofertaId: offer.oferta_id, data: { precio: Number(editPrecio), stock: Number(editStock) } })
  }

  function toggleEstado(offer) {
    const nuevoEstado = offer.estado === 'activa' ? 'pausada' : 'activa'
    updateMutation.mutate({ ofertaId: offer.oferta_id, data: { estado: nuevoEstado } })
  }

  const estadoBadge = { activa: 'success', pausada: 'secondary', descontinuada: 'error', borrador: 'secondary' }

  function fmtVariant(atributos) {
    const entries = Object.entries(atributos || {})
    if (!entries.length) return 'Predeterminada'
    return entries.map(([k, v]) => `${k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}: ${v}`).join(' · ')
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogTitle className="flex items-center gap-2">
          <Layers size={16} /> Ofertas — {product?.nombre}
        </DialogTitle>
        <DialogDescription>
          Las variantes describen combinaciones dinámicas de atributos. Cada vendedor puede tener una oferta por variante.
        </DialogDescription>

        {/* ── Ofertas existentes ── */}
        <div className="space-y-1.5">
          <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
            Ofertas registradas
          </p>
          {isLoading ? (
            <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} className="h-10 w-full" />)}</div>
          ) : offers.length === 0 ? (
            <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] px-4 py-6 text-center font-sans text-sm text-[var(--color-text-muted)]">
              Sin ofertas registradas
            </div>
          ) : (
            <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[640px]">
                  <thead>
                    <tr className="bg-[var(--color-background)] border-b border-[var(--color-border)]">
                      {['Vendedor', 'Variante', 'SKU', 'Precio', 'Stock', 'Estado', ''].map(h => (
                        <th key={h} className="px-3 py-2 text-left font-sans font-semibold text-xs uppercase tracking-wider text-[var(--color-text-muted)] whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {offers.map((offer) => (
                      <tr key={offer.oferta_id} className="border-b border-[var(--color-border)] last:border-0 hover:bg-[var(--color-background)] transition-colors">
                        <td className="px-3 py-2.5 font-sans font-semibold text-[var(--color-text-primary)] whitespace-nowrap">{offer.vendedor_nombre}</td>
                        <td className="px-3 py-2.5">
                          {Object.keys(offer.variante_atributos || {}).length ? (
                            <span className="inline-flex flex-wrap gap-1">
                              {Object.entries(offer.variante_atributos).map(([k, v]) => (
                                <span key={k} className="inline-block rounded bg-[var(--color-border)] px-1.5 py-0.5 text-[11px] font-sans text-[var(--color-text-secondary)]">
                                  {k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}: {v}
                                </span>
                              ))}
                            </span>
                          ) : (
                            <span className="text-xs text-[var(--color-text-muted)] italic">Predeterminada</span>
                          )}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-xs text-[var(--color-text-muted)] whitespace-nowrap">{offer.sku}</td>
                        <td className="px-3 py-2.5 whitespace-nowrap">
                          {editingId === offer.oferta_id ? (
                            <Input type="number" value={editPrecio} onChange={e => setEditPrecio(e.target.value)} className="w-24 h-7 text-xs font-mono" step="0.01" min="0" />
                          ) : (
                            <span className="font-mono font-semibold">{formatQ(offer.precio)}</span>
                          )}
                        </td>
                        <td className="px-3 py-2.5 whitespace-nowrap">
                          {editingId === offer.oferta_id ? (
                            <Input type="number" value={editStock} onChange={e => setEditStock(e.target.value)} className="w-20 h-7 text-xs font-mono" min="0" />
                          ) : (
                            <span className={`font-mono font-semibold ${(offer.stock ?? 0) === 0 ? 'text-[var(--color-error)]' : (offer.stock ?? 0) <= 5 ? 'text-amber-500' : 'text-[var(--color-text-primary)]'}`}>
                              {offer.stock ?? offer.stock_disponible ?? 0}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2.5 whitespace-nowrap">
                          <Badge variant={estadoBadge[offer.estado] || 'secondary'}>{offer.estado}</Badge>
                        </td>
                        <td className="px-3 py-2.5 whitespace-nowrap">
                          <div className="flex items-center gap-1">
                            {editingId === offer.oferta_id ? (
                              <>
                                <Button size="sm" variant="ghost" onClick={() => handleSaveEdit(offer)} disabled={updateMutation.isPending}>Guardar</Button>
                                <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>Cancelar</Button>
                              </>
                            ) : (
                              <>
                                <Button size="sm" variant="ghost" onClick={() => startEdit(offer)} title="Editar precio y stock"><Edit size={12} /></Button>
                                <Button size="sm" variant="ghost" onClick={() => toggleEstado(offer)} disabled={updateMutation.isPending}>
                                  {offer.estado === 'activa' ? 'Pausar' : 'Activar'}
                                </Button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* ── Añadir oferta ── */}
        {availableVendors.length > 0 ? (
          <form onSubmit={handleAdd} className="border border-[var(--color-border)] rounded-[var(--radius-md)] p-4 space-y-3 bg-[var(--color-background)]">
            <p className="font-sans text-sm font-semibold text-[var(--color-text-primary)]">Añadir oferta de otro vendedor</p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div>
                <Label className="text-xs">Variante *</Label>
                <Select value={selectedVariant} onValueChange={setNewVariantId}>
                  <SelectTrigger className="h-8 text-xs mt-1"><SelectValue placeholder="Seleccionar..." /></SelectTrigger>
                  <SelectContent>
                    {variants.map(v => (
                      <SelectItem key={v.variante_id} value={String(v.variante_id)}>
                        {fmtVariant(v.atributos)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Vendedor *</Label>
                <Select value={newVendorId} onValueChange={setNewVendorId}>
                  <SelectTrigger className="h-8 text-xs mt-1"><SelectValue placeholder="Seleccionar..." /></SelectTrigger>
                  <SelectContent>
                    {availableVendors.map(v => (
                      <SelectItem key={v.vendedor_id} value={String(v.vendedor_id)}>
                        {v.nombre_comercial || v.nombre_completo}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Precio (GTQ) *</Label>
                <Input required type="number" step="0.01" min="0.01" value={newPrecio} onChange={e => setNewPrecio(e.target.value)} className="h-8 text-xs mt-1 font-mono" placeholder="0.00" />
              </div>
              <div>
                <Label className="text-xs">Stock inicial *</Label>
                <Input required type="number" min="0" value={newStock} onChange={e => setNewStock(e.target.value)} className="h-8 text-xs mt-1 font-mono" placeholder="0" />
              </div>
            </div>
            <div className="flex justify-end">
              <Button type="submit" size="sm" loading={addMutation.isPending} disabled={!newVendorId || !selectedVariant}>
                <Plus size={13} /> Añadir oferta
              </Button>
            </div>
          </form>
        ) : offers.length > 0 ? (
          <p className="font-sans text-xs text-[var(--color-text-muted)] text-center py-1">
            Todos los vendedores registrados ya tienen una oferta para la variante seleccionada.
          </p>
        ) : null}

        <div className="flex justify-end pt-1">
          <DialogClose asChild><Button variant="secondary" size="sm">Cerrar</Button></DialogClose>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function ProductsSection() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [estado, setEstado] = useState('todos')
  const [modalOpen, setModalOpen] = useState(false)
  const [editProduct, setEditProduct] = useState(null)
  const [offersOpen, setOffersOpen] = useState(false)
  const [offersProduct, setOffersProduct] = useState(null)
  const [variantsOpen, setVariantsOpen] = useState(false)
  const [variantsProduct, setVariantsProduct] = useState(null)
  const PAGE_SIZE = 15
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['admin-products', page, search, estado],
    queryFn: () => getAdminProducts({ page, page_size: PAGE_SIZE, estado, ...(search && { q: search }) }).then((r) => r.data),
    placeholderData: keepPreviousData,
  })

  function handleSearch(e) {
    e.preventDefault()
    setSearch(searchInput.trim())
    setPage(1)
  }

  function clearSearch() {
    setSearchInput('')
    setSearch('')
    setPage(1)
  }

  const deleteMutation = useMutation({
    mutationFn: (id) => deleteProduct(id),
    onSuccess: () => {
      toast.success('Producto descontinuado; permanece disponible en administración.')
      queryClient.invalidateQueries({ queryKey: ['admin-products'] })
      queryClient.invalidateQueries({ queryKey: ['products'] })
      queryClient.invalidateQueries({ queryKey: ['catalog-stats'] })
    },
    onError: () => toast.error('No se pudo eliminar el producto.'),
  })

  function openCreate() { navigate('/admin/products/new') }
  function openEdit(prod) { navigate('/admin/products/'+prod._id) }
  function handleDelete(prod) {
    if (!window.confirm(`¿Descontinuar "${prod.nombre}"? Seguirá visible en administración y conservará su historial.`)) return
    deleteMutation.mutate(prod._id)
  }

  const products = data?.items || []
  const totalPages = data?.total_pages || 1

  if (isLoading) return (
    <div className="space-y-3">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
  )

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <form onSubmit={handleSearch} className="relative flex-1 max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] pointer-events-none" />
          <input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Buscar por nombre o SKU..."
            className="w-full h-9 pl-8 pr-8 bg-[var(--color-background)] border border-[var(--color-border)] rounded-[var(--radius-md)] font-sans text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-action)] focus:ring-2 focus:ring-[var(--color-action)]/20 transition-colors"
          />
          {searchInput && (
            <button type="button" onClick={clearSearch} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]">
              <XIcon size={13} />
            </button>
          )}
        </form>
        {search && (
          <span className="font-sans text-xs text-[var(--color-text-muted)]">
            Resultados para <span className="font-semibold text-[var(--color-text-primary)]">"{search}"</span>
          </span>
        )}
        <div className="w-48">
          <Select value={estado} onValueChange={(value) => { setEstado(value); setPage(1) }}>
            <SelectTrigger><SelectValue placeholder="Todos los estados" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="todos">Todos los estados</SelectItem>
              <SelectItem value="activo">Activos</SelectItem>
              <SelectItem value="inactivo">Inactivos</SelectItem>
              <SelectItem value="descontinuado">Descontinuados</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="ml-auto">
          <Button size="sm" onClick={openCreate}><Plus size={14} /> Nuevo producto</Button>
        </div>
      </div>

      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[var(--color-background)]">
                {['Imagen', 'Nombre', 'Categoría', 'Precio', 'Stock', 'Estado', 'Disponible', 'Acciones'].map((h) => (
                  <th key={h} className="px-4 py-3 text-left font-sans font-semibold text-xs uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)]">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {products.map((prod, idx) => {
                const firstImg = prod.imagenes?.[0]?.url || prod.imagenes?.[0]
                return (
                  <tr key={prod._id} className={cn('border-b border-[var(--color-border)] last:border-0', idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]')}>
                    <td className="px-4 py-2 w-12">
                      {firstImg ? (
                        <img src={firstImg} alt={prod.nombre} className="h-10 w-10 rounded-[var(--radius-sm)] object-cover border border-[var(--color-border)]" />
                      ) : (
                        <div className="h-10 w-10 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-background)] flex items-center justify-center">
                          <ImageIcon size={14} className="text-[var(--color-text-muted)]" />
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 font-display font-semibold text-[var(--color-text-primary)] max-w-[180px]">
                      <Link className="line-clamp-1 text-[var(--color-action)]" to={'/admin/products/'+prod._id}>{prod.nombre}</Link>
                      <span className="font-mono font-normal text-[10px] text-[var(--color-text-muted)] block">{prod.sku}</span>
                    </td>
                    <td className="px-4 py-3 font-sans text-[var(--color-text-secondary)]">{prod.categoria?.nombre || '—'}</td>
                    <td className="px-4 py-3 font-mono font-semibold text-[var(--color-text-primary)]">{formatQ(prod.precio)}</td>
                    <td className="px-4 py-3 font-mono text-sm">
                      {prod.stock == null ? (
                        <span className="text-[var(--color-text-muted)]">—</span>
                      ) : prod.stock === 0 ? (
                        <span className="text-[var(--color-error)] font-semibold">0</span>
                      ) : prod.stock <= 5 ? (
                        <span className="text-[var(--color-warning,#f59e0b)] font-semibold">{prod.stock}</span>
                      ) : (
                        <span className="text-[var(--color-text-primary)]">{prod.stock}</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={prod.estado === 'activo' ? 'success' : prod.estado === 'descontinuado' ? 'error' : 'secondary'}>
                        {prod.estado || 'activo'}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={prod.disponible ? 'success' : 'error'}>{prod.disponible ? 'Sí' : 'No'}</Badge>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" size="sm" onClick={() => openEdit(prod)}><Edit size={13} /> Editar</Button>
                        <Button variant="ghost" size="sm" onClick={() => { navigate('/admin/products/'+prod._id+'?tab=variants') }}>
                          <GitBranch size={13} /> Variantes
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => { navigate('/admin/products/'+prod._id+'?tab=offers') }}>
                          <Layers size={13} /> Ofertas{prod.ofertas_count > 1 ? ` (${prod.ofertas_count})` : ''}
                        </Button>
                        <Button variant="ghost" size="sm" asChild>
                          <Link to={`/admin/products/${prod._id}/history`}><History size={13} /> Historial</Link>
                        </Button>
                        <Button variant="ghost" size="sm" className="text-[var(--color-error)] hover:text-[var(--color-error)] hover:bg-[var(--color-error)]/10" onClick={() => handleDelete(prod)} disabled={deleteMutation.isPending}>
                          <Trash2 size={13} />
                        </Button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-5">
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Anterior</Button>
          <span className="font-sans text-sm text-[var(--color-text-secondary)]">{page} / {totalPages}</span>
          <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Siguiente</Button>
        </div>
      )}

      <ProductFormModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        product={editProduct}
        onDuplicateFound={(id) => { setModalOpen(false); openEdit({ _id: id }) }}
      />
      <VariantsModal open={variantsOpen} onOpenChange={setVariantsOpen} product={variantsProduct} />
      <OffersModal open={offersOpen} onOpenChange={setOffersOpen} product={offersProduct} />
    </div>
  )
}

// ── CategoriesSection ──
function CategoriesSection() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [createOpen, setCreateOpen] = useState(false)
  const [editTarget, setEditTarget] = useState(null)
  const [editOpen, setEditOpen] = useState(false)
  const [searchCat, setSearchCat] = useState('')

  const [newNombre, setNewNombre] = useState('')
  const [newSlug, setNewSlug] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newPadreId, setNewPadreId] = useState('')
  const [newSkuPrefix, setNewSkuPrefix] = useState('')
  const [newAttrs, setNewAttrs] = useState([])
  const [editAttrs, setEditAttrs] = useState([])
  const [editSkuPrefix, setEditSkuPrefix] = useState('')

  const { data: cats = [], isLoading } = useQuery({
    queryKey: ['admin-categories'],
    queryFn: () => getAdminCategories().then((r) => r.data),
  })

  const createMut = useMutation({
    mutationFn: (data) => createCategory(data),
    onSuccess: () => {
      toast.success('Categoría creada.')
      queryClient.invalidateQueries({ queryKey: ['admin-categories'] })
      queryClient.invalidateQueries({ queryKey: ['categories'] })
      setCreateOpen(false)
      setNewNombre(''); setNewSlug(''); setNewDesc(''); setNewPadreId(''); setNewSkuPrefix(''); setNewAttrs([])
    },
    onError: (err) => {
      const detail = err?.response?.data?.detail
      if (err?.response?.status === 409 && detail?.existing_slug) {
        const existingCat = cats.find((c) => c.slug === detail.existing_slug)
        toast.error(detail.message || `Ya existe la categoría "${detail.existing_nombre}".`, {
          action: existingCat ? {
            label: 'Ir a editar',
            onClick: () => { setCreateOpen(false); openEdit(existingCat) },
          } : undefined,
        })
        return
      }
      toast.error(typeof detail === 'string' ? detail : 'Error al crear categoría.')
    },
  })

  const schemaMut = useMutation({
    mutationFn: ({ slug, data }) => updateCategorySchema(slug, data),
    onSuccess: () => {
      toast.success('Esquema actualizado.')
      queryClient.invalidateQueries({ queryKey: ['admin-categories'] })
      queryClient.invalidateQueries({ queryKey: ['category-schema'] })
      setEditOpen(false)
    },
    onError: (err) => toast.error(err?.response?.data?.detail || 'Error al actualizar esquema.'),
  })

  const deleteMut = useMutation({
    mutationFn: (slug) => deleteCategory(slug),
    onSuccess: () => {
      toast.success('Categoría eliminada.')
      queryClient.invalidateQueries({ queryKey: ['admin-categories'] })
      queryClient.invalidateQueries({ queryKey: ['categories'] })
    },
    onError: (err) => toast.error(err?.response?.data?.detail || 'Error al eliminar.'),
  })

  function slugify(str) {
    return str.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  }

  function emptyAttr() {
    return { nombre: '', etiqueta: '', tipo: 'string', requerido: false, placeholder: '' }
  }

  function openEdit(cat) { navigate('/admin/categories/'+cat.slug) }

  const q = searchCat.trim().toLowerCase()
  const filteredCats = q
    ? cats.filter((c) =>
        c.nombre.toLowerCase().includes(q) ||
        c.slug.toLowerCase().includes(q) ||
        (c.sku_prefix || '').toLowerCase().includes(q) ||
        (cats.find((p) => p.id === c.padre_id)?.nombre || '').toLowerCase().includes(q)
      )
    : cats

  function handleDelete(cat) {
    if (!window.confirm(`¿Eliminar categoría "${cat.nombre}"? Esto también eliminará su esquema de campos.`)) return
    deleteMut.mutate(cat.slug)
  }

  if (isLoading) return (
    <div className="space-y-3">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
  )

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 justify-between">
        <div className="relative w-64">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
          <Input
            value={searchCat}
            onChange={(e) => setSearchCat(e.target.value)}
            placeholder="Buscar por nombre, slug o SKU…"
            className="pl-8 h-8 text-sm"
          />
        </div>
        <Button size="sm" onClick={() => navigate('/admin/categories/new')}><Plus size={14} /> Nueva categoría</Button>
      </div>

      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-[var(--color-background)]">
              {['Nombre', 'Slug', 'Prefijo SKU', 'Padre', 'Campos (MongoDB)', 'Acciones'].map((h) => (
                <th key={h} className="px-4 py-3 text-left font-sans font-semibold text-xs uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)]">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filteredCats.map((cat, idx) => (
              <tr key={cat.id} className={cn('border-b border-[var(--color-border)] last:border-0', idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]')}>
                <td className="px-4 py-3 font-display font-semibold text-[var(--color-text-primary)]">
                  <Link to={'/admin/categories/'+cat.slug} className="text-[var(--color-action)]">{cat.nombre}</Link>
                  {!cat.activa && <Badge variant="error" className="ml-2 text-[10px]">inactiva</Badge>}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-[var(--color-text-secondary)]">{cat.slug}</td>
                <td className="px-4 py-3">
                  {cat.sku_prefix
                    ? <span className="font-mono text-xs font-bold px-2 py-0.5 rounded bg-[var(--color-action)]/10 text-[var(--color-action)] border border-[var(--color-action)]/20">{cat.sku_prefix}</span>
                    : <span className="text-[var(--color-text-muted)] text-xs italic">—</span>
                  }
                </td>
                <td className="px-4 py-3 font-sans text-xs text-[var(--color-text-secondary)]">
                  {cat.padre_id ? cats.find((c) => c.id === cat.padre_id)?.nombre || `#${cat.padre_id}` : <span className="text-[var(--color-text-muted)]">—</span>}
                </td>
                <td className="px-4 py-3 font-sans text-[var(--color-text-secondary)]">
                  {cat.atributos.length > 0 ? cat.atributos.map((a) => a.etiqueta).join(', ') : <span className="text-[var(--color-text-muted)] italic">sin campos</span>}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1">
                    <Button variant="ghost" size="sm" onClick={() => openEdit(cat)}><Edit size={13} /> Editar campos</Button>
                    <Button variant="ghost" size="sm" className="text-[var(--color-error)] hover:text-[var(--color-error)] hover:bg-[var(--color-error)]/10" onClick={() => handleDelete(cat)} disabled={deleteMut.isPending}>
                      <Trash2 size={13} />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
            {filteredCats.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-8 text-center font-sans text-sm text-[var(--color-text-muted)]">
                {q ? `Sin resultados para "${searchCat}".` : 'No hay categorías todavía.'}
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ── Crear categoría ── */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogTitle>Nueva categoría</DialogTitle>
          <DialogDescription>Los datos básicos se guardan en MySQL. Los campos personalizados se guardan en MongoDB.</DialogDescription>
          <form className="space-y-4 mt-2" onSubmit={(e) => {
            e.preventDefault()
            createMut.mutate({ nombre: newNombre, slug: newSlug || slugify(newNombre), descripcion: newDesc || undefined, padre_id: newPadreId ? Number(newPadreId) : undefined, sku_prefix: newSkuPrefix.trim().toUpperCase() || undefined, atributos: newAttrs.filter((a) => a.nombre && a.etiqueta) })
          }}>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Nombre</Label>
                <Input required value={newNombre} onChange={(e) => { setNewNombre(e.target.value); if (!newSlug) setNewSlug(slugify(e.target.value)) }} placeholder="ej. Laptops" />
              </div>
              <div className="space-y-1">
                <Label>Slug (URL)</Label>
                <Input required value={newSlug} onChange={(e) => setNewSlug(e.target.value)} placeholder="ej. laptops" className="font-mono text-sm" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Prefijo SKU <span className="text-[var(--color-text-muted)] font-normal">(3 letras)</span></Label>
                <Input
                  value={newSkuPrefix}
                  onChange={(e) => setNewSkuPrefix(e.target.value.replace(/[^a-zA-Z]/g, '').toUpperCase().slice(0, 3))}
                  placeholder="ej. LAP"
                  maxLength={3}
                  className="font-mono text-sm tracking-widest uppercase"
                />
              </div>
              <div className="space-y-1">
                <Label>Descripción (opcional)</Label>
                <Input value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="Breve descripción..." />
              </div>
            </div>
            <div className="space-y-1">
              <Label>Categoría padre (opcional)</Label>
              <Select value={newPadreId || '__root__'} onValueChange={value => setNewPadreId(value === '__root__' ? '' : value)}>
                <SelectTrigger><SelectValue placeholder="Ninguna (categoría raíz)" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__root__">Ninguna (categoría raíz)</SelectItem>
                  {cats.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.nombre}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <Separator />
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Campos personalizados (MongoDB)</p>
                <Button type="button" variant="secondary" size="sm" onClick={() => setNewAttrs((a) => [...a, emptyAttr()])}><Plus size={13} /> Agregar campo</Button>
              </div>
              <p className="font-sans text-xs text-[var(--color-text-muted)]">Estos campos aparecerán al crear/editar productos de esta categoría.</p>
              {newAttrs.length === 0 && <p className="font-sans text-xs text-[var(--color-text-muted)] italic py-2">Sin campos aún. Agrega los atributos que diferencian esta categoría.</p>}
              <div className="space-y-2">
                {newAttrs.map((attr, i) => (
                  <AttrRow key={i} attr={attr} onChange={(updated) => setNewAttrs((a) => a.map((x, j) => j === i ? updated : x))} onRemove={() => setNewAttrs((a) => a.filter((_, j) => j !== i))} />
                ))}
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <DialogClose asChild><Button type="button" variant="secondary">Cancelar</Button></DialogClose>
              <Button type="submit" loading={createMut.isPending}>Crear categoría</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* ── Editar esquema ── */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogTitle>Editar campos — {editTarget?.nombre}</DialogTitle>
          <DialogDescription>Modifica los campos personalizados de esta categoría (solo MongoDB).</DialogDescription>
          <form className="space-y-4 mt-2" onSubmit={(e) => {
            e.preventDefault()
            schemaMut.mutate({ slug: editTarget.slug, data: { atributos: editAttrs.filter((a) => a.nombre && a.etiqueta), sku_prefix: editSkuPrefix.trim().toUpperCase() || null } })
          }}>
            <div className="space-y-1">
              <Label>Prefijo SKU <span className="text-[var(--color-text-muted)] font-normal">(3 letras)</span></Label>
              <Input
                value={editSkuPrefix}
                onChange={(e) => setEditSkuPrefix(e.target.value.replace(/[^a-zA-Z]/g, '').toUpperCase().slice(0, 3))}
                placeholder="ej. LAP"
                maxLength={3}
                className="font-mono text-sm tracking-widest uppercase w-28"
              />
            </div>
            <Separator />
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Campos personalizados</p>
                <Button type="button" variant="secondary" size="sm" onClick={() => setEditAttrs((a) => [...a, emptyAttr()])}><Plus size={13} /> Agregar campo</Button>
              </div>
              {editAttrs.length === 0 && <p className="font-sans text-xs text-[var(--color-text-muted)] italic py-2">Sin campos. Agrega los atributos de esta categoría.</p>}
              <div className="space-y-2">
                {editAttrs.map((attr, i) => (
                  <AttrRow key={i} attr={attr} onChange={(updated) => setEditAttrs((a) => a.map((x, j) => j === i ? updated : x))} onRemove={() => setEditAttrs((a) => a.filter((_, j) => j !== i))} />
                ))}
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <DialogClose asChild><Button type="button" variant="secondary">Cancelar</Button></DialogClose>
              <Button type="submit" loading={schemaMut.isPending}>Guardar esquema</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── OrdersSection ──
function OrdersSection() {
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState('')
  const [updatingId, setUpdatingId] = useState(null)
  const queryClient = useQueryClient()
  const PAGE_SIZE = 20

  const { data, isLoading } = useQuery({
    queryKey: ['admin-orders', page, statusFilter],
    queryFn: () => getAdminOrders(page, PAGE_SIZE, statusFilter || null).then(r => r.data),
    placeholderData: keepPreviousData,
  })

  const statusMutation = useMutation({
    mutationFn: ({ pedidoId, estado }) => updateAdminOrderStatus(pedidoId, estado),
    onSuccess: (_, { pedidoId, estado }) => {
      toast.success(`Pedido #${pedidoId} → ${ESTADO_LABEL[estado] || estado}`)
      queryClient.invalidateQueries({ queryKey: ['admin-orders'] })
      setUpdatingId(null)
    },
    onError: (err) => {
      toast.error(err?.response?.data?.detail || 'Error al cambiar el estado.')
      setUpdatingId(null)
    },
  })

  function handleStatusChange(pedidoId, estado) {
    setUpdatingId(pedidoId)
    statusMutation.mutate({ pedidoId, estado })
  }

  const pedidos = data?.items || []
  const totalPages = data?.total_pages || 1

  return (
    <div className="space-y-4">
      {/* Filter */}
      <div className="flex items-center gap-3">
        <Select value={statusFilter || '__all__'} onValueChange={(v) => { setStatusFilter(v === '__all__' ? '' : v); setPage(1) }}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="Todos los estados" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">Todos</SelectItem>
            <SelectItem value="pendiente">Pendiente</SelectItem>
            <SelectItem value="confirmado">Confirmado</SelectItem>
            <SelectItem value="preparando">En preparación</SelectItem>
            <SelectItem value="enviado_parcial">Envío parcial</SelectItem>
            <SelectItem value="entregado_parcial">Entrega parcial</SelectItem>
            <SelectItem value="enviado">Enviado</SelectItem>
            <SelectItem value="entregado">Entregado</SelectItem>
            <SelectItem value="cancelado">Cancelado</SelectItem>
            <SelectItem value="reembolsado">Reembolsado</SelectItem>
          </SelectContent>
        </Select>
        <span className="font-sans text-xs text-[var(--color-text-muted)]">{data?.total ?? 0} pedidos</span>
      </div>

      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[var(--color-background)]">
                {['Pedido #', 'Fecha', 'Comprador', 'Total', 'Estado actual', 'Detalle y envíos'].map((h) => (
                  <th key={h} className="px-4 py-3 text-left font-sans font-semibold text-xs uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)] whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading
                ? Array.from({ length: 6 }).map((_, i) => (
                    <tr key={i}><td colSpan={6} className="px-4 py-2"><Skeleton className="h-8 w-full" /></td></tr>
                  ))
                : pedidos.length === 0
                  ? <tr><td colSpan={6} className="px-4 py-10 text-center font-sans text-sm text-[var(--color-text-muted)]">Sin pedidos.</td></tr>
                  : pedidos.map((p, idx) => (
                      <tr key={p.id} className={cn('border-b border-[var(--color-border)] last:border-0', idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]')}>
                        <td className="px-4 py-3 font-mono font-semibold text-[var(--color-text-primary)]"><Link to={'/admin/orders/'+p.id}>#{p.id}</Link></td>
                        <td className="px-4 py-3 font-sans text-xs text-[var(--color-text-secondary)] whitespace-nowrap">{formatDate(p.fecha)}</td>
                        <td className="px-4 py-3">
                          <p className="font-display font-semibold text-xs text-[var(--color-text-primary)]">{p.comprador?.nombre}</p>
                          <p className="font-sans text-[10px] text-[var(--color-text-muted)]">{p.comprador?.email}</p>
                        </td>
                        <td className="px-4 py-3 font-mono font-bold text-[var(--color-text-primary)]">{formatQ(p.total)}</td>
                        <td className="px-4 py-3">
                          <Badge variant={ESTADO_BADGE[p.estado] || 'default'}>{ESTADO_LABEL[p.estado] || p.estado}</Badge>
                        </td>
                        <td className="px-4 py-3 w-44">
                          <Button variant="secondary" size="sm" asChild><Link to={'/admin/orders/'+p.id}>Abrir pedido</Link></Button>
                        </td>
                      </tr>
                    ))
              }
            </tbody>
          </table>
        </div>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3">
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Anterior</Button>
          <span className="font-sans text-sm text-[var(--color-text-secondary)]">{page} / {totalPages}</span>
          <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Siguiente</Button>
        </div>
      )}
    </div>
  )
}

// ── UsersSection ──
function UsersSection() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [searchUser, setSearchUser] = useState('')
  const queryClient = useQueryClient()

  const [vpOpen, setVpOpen] = useState(false)
  const [vpUser, setVpUser] = useState(null)
  const [vpNombre, setVpNombre] = useState('')
  const [vpNit, setVpNit] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['admin-users', page],
    queryFn: () => getAdminUsers(page).then((r) => r.data),
    placeholderData: keepPreviousData,
  })

  const { data: vendorsData } = useQuery({
    queryKey: ['admin-vendors'],
    queryFn: () => getAdminVendors().then((r) => r.data),
  })
  const vendorByUserId = Object.fromEntries((vendorsData || []).map((v) => [v.usuario_id, v]))

  const mutation = useMutation({
    mutationFn: ({ userId, roles }) => updateUserRoles(userId, roles),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-users'] }),
    onError: (err) => toast.error(err?.response?.data?.detail || 'No se pudo actualizar los roles.'),
  })

  const vpMutation = useMutation({
    mutationFn: ({ userId, data }) => setVendorProfile(userId, data),
    onSuccess: () => {
      toast.success('Perfil de vendedor guardado.')
      setVpOpen(false)
      queryClient.invalidateQueries({ queryKey: ['admin-vendors'] })
    },
    onError: (err) => toast.error(err?.response?.data?.detail || 'Error al guardar perfil.'),
  })

  const tiendayaMutation = useMutation({
    mutationFn: (vendedorId) => setTiendayaVendor(vendedorId),
    onSuccess: (res) => {
      const { vendedor_id, es_tiendaya } = res.data
      queryClient.setQueryData(['admin-vendors'], (old) =>
        old?.map((v) =>
          v.vendedor_id === vendedor_id
            ? { ...v, es_tiendaya }
            : { ...v, es_tiendaya: es_tiendaya ? false : v.es_tiendaya }
        )
      )
      toast.success(es_tiendaya ? 'Vendedor marcado como TiendaYa.' : 'Marca TiendaYa removida.')
      queryClient.invalidateQueries({ queryKey: ['admin-vendors'], refetchType: 'none' })
    },
    onError: (err) => toast.error(err?.response?.data?.detail || 'Error al actualizar TiendaYa.'),
  })

  function toggleRole(user, role) {
    const current = new Set(user.roles)
    if (current.has(role)) current.delete(role)
    else current.add(role)
    mutation.mutate({ userId: user.id, roles: [...current] })
  }

  const users = data?.items || []
  const totalPages = data?.total_pages || 1

  const uq = searchUser.trim().toLowerCase()
  const filteredUsers = uq
    ? users.filter((u) =>
        `${u.nombre} ${u.apellido}`.toLowerCase().includes(uq) ||
        u.email.toLowerCase().includes(uq) ||
        u.roles.some((r) => r.toLowerCase().includes(uq)) ||
        (vendorByUserId[u.id]?.nombre_comercial || '').toLowerCase().includes(uq)
      )
    : users

  if (isLoading) return (
    <div className="space-y-3">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-14 w-full" />)}</div>
  )

  return (
    <div className="space-y-4">
      <div className="relative w-72">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
        <Input
          value={searchUser}
          onChange={(e) => { setSearchUser(e.target.value); setPage(1) }}
          placeholder="Buscar por nombre, email o rol…"
          className="pl-8 h-8 text-sm"
        />
      </div>
      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[var(--color-background)]">
                {['Usuario', 'Email', 'Estado', 'Roles (clic para cambiar)', 'Acciones'].map((h) => (
                  <th key={h} className="px-4 py-3 text-left font-sans font-semibold text-xs uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)] whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredUsers.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-8 text-center font-sans text-sm text-[var(--color-text-muted)]">
                  {uq ? `Sin resultados para "${searchUser}".` : 'No hay usuarios todavía.'}
                </td></tr>
              )}
              {filteredUsers.map((user, idx) => (
                <tr key={user.id} className={cn('border-b border-[var(--color-border)] last:border-0', idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]')}>
                  <td className="px-4 py-3">
                    <p className="font-display font-semibold text-[var(--color-text-primary)]"><Link to={'/admin/users/'+user.id} className="text-[var(--color-action)]">{user.nombre} {user.apellido}</Link></p>
                    <p className="font-mono text-[10px] text-[var(--color-text-muted)]">#{user.id}</p>
                    {user.roles.includes('vendedor') && vendorByUserId[user.id]?.nombre_comercial && (
                      <p className="font-sans text-[10px] text-[var(--color-text-secondary)] mt-0.5">
                        {vendorByUserId[user.id].nombre_comercial}
                        {vendorByUserId[user.id].nit && <span className="font-mono ml-1 text-[var(--color-text-muted)]">· {vendorByUserId[user.id].nit}</span>}
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-3 font-sans text-[var(--color-text-secondary)] text-xs">{user.email}</td>
                  <td className="px-4 py-3"><Badge variant={user.estado === 'activo' ? 'success' : 'error'}>{user.estado}</Badge></td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1.5">
                      {ALL_ROLES.map((role) => {
                        const meta = ROLE_META[role]
                        const { Icon } = meta
                        const hasRole = user.roles.includes(role)
                        return (
                          <button key={role} onClick={() => toggleRole(user, role)} disabled={mutation.isPending}
                            className={cn('inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-sans font-semibold border transition-all duration-150 disabled:opacity-50', hasRole ? meta.active : meta.inactive)}>
                            <Icon size={11} strokeWidth={2} />
                            {meta.label}
                          </button>
                        )
                      })}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {user.roles.includes('vendedor') && (
                      <div className="flex flex-col gap-1.5 items-start">
                        <Button variant="ghost" size="sm" onClick={() => {
                          navigate(vendorByUserId[user.id]?.vendedor_id ? '/admin/vendors/'+vendorByUserId[user.id].vendedor_id : '/admin/users/'+user.id)
                        }}>
                          <Store size={13} /> Perfil vendedor
                        </Button>
                        {vendorByUserId[user.id]?.vendedor_id && (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={tiendayaMutation.isPending}
                            onClick={() => tiendayaMutation.mutate(vendorByUserId[user.id].vendedor_id)}
                            className={cn(
                              vendorByUserId[user.id]?.es_tiendaya
                                ? 'text-amber-500 hover:text-amber-600 hover:bg-amber-50'
                                : 'text-[var(--color-text-muted)] hover:text-amber-500 hover:bg-amber-50'
                            )}
                            title={vendorByUserId[user.id]?.es_tiendaya ? 'Quitar marca TiendaYa' : 'Marcar como vendedor TiendaYa'}
                          >
                            <Star size={13} fill={vendorByUserId[user.id]?.es_tiendaya ? 'currentColor' : 'none'} />
                            {vendorByUserId[user.id]?.es_tiendaya ? 'TiendaYa' : 'Marcar TiendaYa'}
                          </Button>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {!uq && totalPages > 1 && (
        <div className="flex items-center justify-center gap-3">
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Anterior</Button>
          <span className="font-sans text-sm text-[var(--color-text-secondary)]">{page} / {totalPages}</span>
          <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Siguiente</Button>
        </div>
      )}

      <Dialog open={vpOpen} onOpenChange={setVpOpen}>
        <DialogContent className="max-w-sm">
          <DialogTitle>Perfil de vendedor — {vpUser?.nombre} {vpUser?.apellido}</DialogTitle>
          <DialogDescription>Configura el nombre comercial y NIT del vendedor.</DialogDescription>
          <form className="space-y-4 mt-2" onSubmit={(e) => { e.preventDefault(); vpMutation.mutate({ userId: vpUser.id, data: { nombre_comercial: vpNombre, nit: vpNit } }) }}>
            <div>
              <Label>Nombre comercial *</Label>
              <Input required value={vpNombre} onChange={e => setVpNombre(e.target.value)} placeholder="Ej: TechStore Guatemala" />
            </div>
            <div>
              <Label>NIT *</Label>
              <Input required value={vpNit} onChange={e => setVpNit(e.target.value)} placeholder="Ej: 1234567-8" className="font-mono" />
            </div>
            <div className="flex justify-end gap-2">
              <DialogClose asChild><Button type="button" variant="secondary">Cancelar</Button></DialogClose>
              <Button type="submit" loading={vpMutation.isPending}>Guardar</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── SalesSection ──
function SalesSection() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [expandedId, setExpandedId] = useState(null)
  const [exporting, setExporting] = useState(false)
  const PAGE_SIZE = 15

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['admin-sales-stats'],
    queryFn: () => getAdminSalesStats().then((r) => r.data),
  })

  const { data: salesData, isLoading: salesLoading } = useQuery({
    queryKey: ['admin-sales', page],
    queryFn: () => getAdminSales(page, PAGE_SIZE).then((r) => r.data),
    placeholderData: keepPreviousData,
  })

  async function handleExport() {
    setExporting(true)
    try {
      const res = await exportAdminSalesExcel()
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url
      a.download = 'ventas-TiendaYa.xlsx'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      toast.success('Excel exportado correctamente.')
    } catch {
      toast.error('No se pudo exportar a Excel.')
    } finally {
      setExporting(false)
    }
  }

  const pedidos = salesData?.items || []
  const totalPages = salesData?.total_pages || 1

  const lineData = (stats?.ingresos_por_dia || []).map((d) => ({
    fecha: d.fecha.slice(5),
    total: d.total,
  }))

  const pieData = (stats?.por_estado || []).map((e) => ({
    name: ESTADO_LABEL[e.estado] || e.estado,
    value: e.cantidad,
    color: ESTADO_CHART_COLORS[e.estado] || '#6b7280',
  }))

  const barData = (stats?.top_vendedores || []).map((v) => ({
    nombre: v.nombre,
    ingresos: v.ingresos,
  }))

  return (
    <div className="space-y-6">
      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {statsLoading
          ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 w-full" />)
          : <>
              <StatCard label="Total pedidos" value={stats?.total_pedidos ?? '—'} />
              <StatCard label="Ingresos totales" value={stats ? formatQ(stats.total_ingresos) : '—'} sub="Sin cancelados/reembolsados" />
              <StatCard label="Promedio por pedido" value={stats ? formatQ(stats.promedio_pedido) : '—'} />
              <StatCard label="Pendientes" value={stats?.pendientes ?? '—'} />
            </>
        }
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5">
          <h3 className="font-display font-semibold text-base text-[var(--color-text-primary)] mb-4">Ingresos — últimos 30 días</h3>
          {statsLoading ? <Skeleton className="h-48 w-full" /> : (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={lineData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="fecha" tick={{ fontSize: 10, fill: 'var(--color-text-muted)' }} interval={4} />
                <YAxis tick={{ fontSize: 10, fill: 'var(--color-text-muted)' }} tickFormatter={(v) => `Q${v}`} width={64} />
                <Tooltip formatter={(v) => [formatQ(v), 'Ingresos']} contentStyle={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', fontSize: 12 }} />
                <Line type="monotone" dataKey="total" stroke="var(--color-action)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5">
          <h3 className="font-display font-semibold text-base text-[var(--color-text-primary)] mb-4">Por estado</h3>
          {statsLoading ? <Skeleton className="h-48 w-full" /> : (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="45%" outerRadius={65}>
                  {pieData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                </Pie>
                <Legend iconSize={10} iconType="circle" wrapperStyle={{ fontSize: 11 }} />
                <Tooltip formatter={(v, name) => [`${v} pedidos`, name]} contentStyle={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Top vendors bar chart */}
      {barData.length > 0 && (
        <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5">
          <h3 className="font-display font-semibold text-base text-[var(--color-text-primary)] mb-4">Top vendedores por ingresos</h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={barData} layout="vertical" margin={{ left: 0, right: 16, top: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: 'var(--color-text-muted)' }} tickFormatter={(v) => `Q${v}`} />
              <YAxis type="category" dataKey="nombre" tick={{ fontSize: 11, fill: 'var(--color-text-primary)' }} width={120} />
              <Tooltip formatter={(v) => [formatQ(v), 'Ingresos']} contentStyle={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', fontSize: 12 }} />
              <Bar dataKey="ingresos" fill="var(--color-jade)" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Sales table */}
      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
        <div className="px-5 py-4 border-b border-[var(--color-border)] flex items-center justify-between">
          <h3 className="font-display font-semibold text-base text-[var(--color-text-primary)]">Ventas recientes</h3>
          <Button variant="secondary" size="sm" onClick={handleExport} loading={exporting}>
            <FileSpreadsheet size={14} /> Exportar Excel
          </Button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[var(--color-background)]">
                {['', 'Pedido #', 'Fecha', 'Comprador', 'Total', 'Estado', 'Método pago'].map((h, i) => (
                  <th key={i} className="px-4 py-3 text-left font-sans font-semibold text-xs uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)] whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {salesLoading
                ? Array.from({ length: 6 }).map((_, i) => (
                    <tr key={i}><td colSpan={7} className="px-4 py-2"><Skeleton className="h-8 w-full" /></td></tr>
                  ))
                : pedidos.length === 0
                  ? <tr><td colSpan={7} className="px-4 py-10 text-center font-sans text-sm text-[var(--color-text-muted)]">Sin ventas todavía.</td></tr>
                  : pedidos.map((pedido, idx) => {
                      const isExpanded = expandedId === pedido.id
                      return (
                        <React.Fragment key={pedido.id}>
                          <tr
                            className={cn('border-b border-[var(--color-border)] cursor-pointer hover:bg-[var(--color-background)]/60', idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]')}
                            onClick={() => navigate('/admin/sales/'+pedido.id)}
                          >
                            <td className="px-4 py-3 text-[var(--color-text-muted)]">
                              {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                            </td>
                            <td className="px-4 py-3 font-mono font-semibold text-[var(--color-text-primary)]">#{pedido.id}</td>
                            <td className="px-4 py-3 font-sans text-xs text-[var(--color-text-secondary)] whitespace-nowrap">{formatDate(pedido.fecha)}</td>
                            <td className="px-4 py-3">
                              <p className="font-display font-semibold text-xs text-[var(--color-text-primary)]">{pedido.comprador?.nombre}</p>
                              <p className="font-sans text-[10px] text-[var(--color-text-muted)]">{pedido.comprador?.email}</p>
                            </td>
                            <td className="px-4 py-3 font-mono font-bold text-[var(--color-text-primary)]">{formatQ(pedido.total)}</td>
                            <td className="px-4 py-3">
                              <Badge variant={ESTADO_BADGE[pedido.estado] || 'default'}>
                                {ESTADO_LABEL[pedido.estado] || pedido.estado}
                              </Badge>
                            </td>
                            <td className="px-4 py-3 font-sans text-xs text-[var(--color-text-secondary)]">
                              {pedido.pago?.metodo || '—'}
                            </td>
                          </tr>
                          {isExpanded && (
                            <tr className="bg-[var(--color-background)]">
                              <td colSpan={7} className="px-8 py-3">
                                <table className="w-full text-xs border border-[var(--color-border)] rounded-[var(--radius-md)] overflow-hidden">
                                  <thead>
                                    <tr className="bg-[var(--color-border)]/30">
                                      {['Producto', 'Vendedor', 'Precio unit.', 'Cant.', 'Subtotal'].map((h) => (
                                        <th key={h} className="px-3 py-2 text-left font-sans font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">{h}</th>
                                      ))}
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {pedido.lineas.map((l, j) => (
                                      <tr key={j} className={j % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]'}>
                                        <td className="px-3 py-2 font-display font-medium text-[var(--color-text-primary)]">{l.producto_nombre}</td>
                                        <td className="px-3 py-2 font-sans text-[var(--color-text-secondary)]">
                                          {l.vendedor || <span className="text-[var(--color-text-muted)]">—</span>}
                                        </td>
                                        <td className="px-3 py-2 font-mono">{formatQ(l.precio_unitario)}</td>
                                        <td className="px-3 py-2 font-mono">{l.cantidad}</td>
                                        <td className="px-3 py-2 font-mono font-semibold">{formatQ(l.subtotal_linea)}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      )
                    })
              }
            </tbody>
          </table>
        </div>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3">
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Anterior</Button>
          <span className="font-sans text-sm text-[var(--color-text-secondary)]">{page} / {totalPages}</span>
          <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Siguiente</Button>
        </div>
      )}
    </div>
  )
}

const fraudValue = value => value === null || value === undefined || value === '' ? 'No disponible' : value
const fraudDate = value => value ? formatDate(value) : 'No disponible'

const FRAUD_GUIDE = {
  bombardeo: ['Cinco o más reseñas verificadas y aprobadas sobre un producto en 24 horas.', 'Neo4j identifica el patrón; MySQL aporta el texto y los datos autoritativos.', 'La concentración temporal no demuestra que las reseñas sean falsas.'],
  reviewer_unico_vendedor: ['Un cliente concentra al menos tres reseñas verificadas en una sola tienda.', 'Neo4j identifica la concentración; MySQL aporta cada reseña.', 'No es una autocompra ni demuestra coordinación por sí sola.'],
  cluster: ['Un par de clientes reseñó al menos tres productos en común.', 'Neo4j encuentra el par y los productos; MySQL aporta ambas reseñas.', 'No compara igualdad de textos o calificaciones ni identifica necesariamente un grupo independiente.'],
  sin_compra: ['Una reseña no tiene respaldo suficiente de compra pagada válida.', 'MySQL conserva la reseña, su moderación y el motivo de verificación; Neo4j aporta el nombre del producto.', 'No demuestra que la compra nunca haya ocurrido.'],
  autocompra: ['El comprador coincide con el propietario actual de la tienda receptora.', 'Neo4j identifica la relación; MySQL aporta pedidos, pagos y reseñas disponibles.', 'No existe historial temporal completo de propiedad de la tienda.'],
  inventario_atipico: ['Entradas o ajustes positivos reiterados cerca de ventas pagadas.', 'MySQL aporta los movimientos, responsables y pedidos asociados.', 'La correlación de F06 es temporal; no exige cantidades iguales ni prueba fraude.'],
  coincidencia_cantidad: ['Una compra pagada y una reposición posterior de la misma oferta y cantidad forman un par 1:1.', 'MySQL aporta las líneas pagadas y movimientos confirmados por la regla.', 'Los candidatos ambiguos se excluyen; la coincidencia no demuestra causalidad.'],
}

function FraudGuide({ type, segment }) {
  const guide = FRAUD_GUIDE[type]
  if (!guide) return null
  const historical = segment === 'historicas_no_verificadas'
  return <div className="rounded border border-violet-200 bg-violet-50 p-3 text-xs text-violet-950 space-y-1">
    <p><strong>Qué se detectó:</strong> {historical ? `El mismo patrón F01–F03 aplicado a reseñas históricas no verificadas. ${type === 'bombardeo' ? 'Ventana de 24 horas y umbral de cinco reseñas.' : ''}` : guide[0]}</p>
    <p><strong>Registros y fuente:</strong> {guide[1]}</p>
    <p><strong>Límite:</strong> {guide[2]}</p>
  </div>
}

function FraudReviewCard({ review, productName }) {
  return <article className="rounded border border-[var(--color-border)] bg-[var(--color-background)] p-3 text-xs space-y-1">
    <div className="flex flex-wrap justify-between gap-2"><strong>{fraudValue(review.usuario_nombre || review.cliente)}</strong><span>{fraudDate(review.fecha)}</span></div>
    {productName && <p>Producto: {productName}</p>}
    <p aria-label={`Calificación ${fraudValue(review.calificacion)} de 5`} className="text-amber-600 font-semibold">{'★'.repeat(Math.max(0, Math.min(5, Number(review.calificacion) || 0)))}{'☆'.repeat(Math.max(0, 5 - (Number(review.calificacion) || 0)))} <span className="text-[var(--color-text-secondary)]">{fraudValue(review.calificacion)}/5</span></p>
    <p className="whitespace-pre-wrap">{review.comentario || 'Sin comentario escrito.'}</p>
    <p>Compra verificada: {review.verificada ? 'Sí' : 'No'}{review.estado ? ` · Moderación: ${review.estado}` : ''}</p>
    <p className="font-mono text-[11px] text-[var(--color-text-muted)]">Reseña {fraudValue(review.resena_id)}</p>
  </article>
}

function FraudEvidence({ alert }) {
  const e = alert.evidencias || {}
  const d = alert.detalle_investigacion || {}
  if (alert.tipo === 'autocompra') return <div className="space-y-3 text-xs">
    <FraudGuide type="autocompra" />
    <p><strong>Comprador:</strong> {fraudValue(alert.usuario_nombre || e.usuario_nombre)} · <strong>Tienda:</strong> {fraudValue(alert.vendedor_nombre || e.vendedor_nombre)} · <strong>Producto:</strong> {fraudValue(alert.producto_nombre || e.producto_nombre)} · <strong>Oferta:</strong> #{fraudValue(alert.oferta_id)}</p>
    <p>El comprador coincide con el propietario <strong>actual</strong> registrado; la propiedad histórica no está verificada.</p>
    <h4 className="font-semibold">Compras relacionadas ({d.compras?.length ?? 0})</h4>
    {d.compras?.length ? <div className="overflow-x-auto"><table className="w-full text-left"><thead><tr>{['Pedido / línea', 'Producto', 'Cantidad', 'Pago', 'Fecha de pago', 'Importe'].map(h => <th key={h} className="p-2 border-b">{h}</th>)}</tr></thead><tbody>{d.compras.map(c => <tr key={c.linea_id}><td className="p-2 border-b">#{c.pedido_id} / #{c.linea_id}</td><td className="p-2 border-b">{fraudValue(c.producto_nombre)}</td><td className="p-2 border-b">{c.cantidad}</td><td className="p-2 border-b">{fraudValue(c.estado_pago)} · {fraudValue(c.estado_pedido)}</td><td className="p-2 border-b">{fraudDate(c.fecha)}</td><td className="p-2 border-b">{c.importe != null ? `Q${c.importe}` : 'No disponible'}</td></tr>)}</tbody></table></div> : <p>No se encontraron líneas autoritativas para los identificadores proyectados.</p>}
    {!!d.resenas?.length && <><h4 className="font-semibold">Reseñas vinculadas</h4>{d.resenas.map(r => <FraudReviewCard key={r.resena_id} review={r} />)}</>}
  </div>
  if (alert.tipo === 'inventario_atipico') {
    const exits = new Map((d.salidas || []).map(m => [m.movimiento_id, m]))
    const entries = new Map((d.movimientos || []).map(m => [m.movimiento_id, m]))
    return <div className="space-y-3 text-xs">
      <FraudGuide type="inventario_atipico" />
      <p><strong>Tienda:</strong> {fraudValue(alert.vendedor_nombre)} · <strong>Producto:</strong> {fraudValue(alert.producto_nombre || alert.producto_ref)} · <strong>Oferta:</strong> #{fraudValue(alert.oferta_id)}</p>
      <div className="flex flex-wrap gap-3"><span>Movimientos positivos: <strong>{fraudValue(e.movimientos)}</strong></span><span>Unidades añadidas: <strong>{fraudValue(e.unidades_positivas)}</strong></span><span>Ajustes manuales: <strong>{e.ajustes_manuales?.length ?? 0}</strong></span><span>Por propietario: <strong>{e.movimientos_por_propietario?.length ?? 0}</strong></span></div>
      <h4 className="font-semibold">Movimientos positivos</h4>
      {d.movimientos?.length ? <div className="overflow-x-auto"><table className="w-full text-left"><thead><tr>{['Fecha', 'Tipo', 'Cantidad', 'Responsable', 'Motivo', 'Movimiento'].map(h => <th key={h} className="p-2 border-b">{h}</th>)}</tr></thead><tbody>{d.movimientos.map(m => <tr key={m.movimiento_id}><td className="p-2 border-b">{fraudDate(m.fecha)}</td><td className="p-2 border-b">{fraudValue(m.tipo)}</td><td className="p-2 border-b">{m.cantidad}</td><td className="p-2 border-b">{fraudValue(m.responsable_nombre)}</td><td className="p-2 border-b">{fraudValue(m.motivo)}</td><td className="p-2 border-b">#{m.movimiento_id}</td></tr>)}</tbody></table></div> : <p>No hay detalle de movimientos en esta evidencia.</p>}
      {!!e.pares_salida_reposicion?.length && <><h4 className="font-semibold">Correlaciones temporales con ventas pagadas</h4>{e.pares_salida_reposicion.map(([exitId, entryId], i) => { const sale = exits.get(exitId); const entry = entries.get(entryId); return <p key={`${exitId}-${entryId}-${i}`} className="rounded border p-2">Pedido #{fraudValue(sale?.pedido_id)} · salida #{exitId}, {fraudValue(sale?.cantidad)} unidades ({fraudDate(sale?.fecha)}) → reposición #{entryId}, {fraudValue(entry?.cantidad)} unidades ({fraudDate(entry?.fecha)}). Correlación temporal, no coincidencia exacta exigida.</p> })}</>}
    </div>
  }
  if (alert.tipo === 'coincidencia_cantidad') return <div className="space-y-3 text-xs">
    <FraudGuide type="coincidencia_cantidad" />
    <p><strong>Tienda:</strong> {fraudValue(alert.vendedor_nombre)} · <strong>Producto:</strong> {fraudValue(alert.producto_nombre || alert.producto_ref)} · <strong>Oferta:</strong> #{fraudValue(alert.oferta_id)}</p>
    {(e.pares_confirmados || []).map((pair, i) => <div key={`${pair.linea_id}-${pair.movimiento_id}-${i}`} className="grid md:grid-cols-2 gap-3 rounded border p-3">
      <div><h4 className="font-semibold">Compra pagada</h4><p>{fraudValue(pair.comprador_nombre)} · pedido #{pair.pedido_id} · línea #{pair.linea_id}</p><p>Oferta #{pair.oferta_id} · {pair.cantidad} unidades · {fraudDate(pair.fecha_compra)}</p></div>
      <div><h4 className="font-semibold">Entrada posterior</h4><p>Movimiento #{pair.movimiento_id} · {fraudValue(pair.tipo_movimiento)} · {pair.cantidad} unidades</p><p>{fraudValue(pair.responsable_movimiento_nombre)} · {fraudDate(pair.fecha_reposicion)} · {fraudValue(pair.motivo_movimiento)}</p></div>
      <p className="md:col-span-2 text-emerald-700 font-semibold">Misma oferta · cantidad idéntica · reposición posterior · {fraudValue(pair.dias_transcurridos)} días transcurridos</p>
    </div>)}
    {!e.pares_confirmados?.length && <p>Sin pares confirmados en esta evidencia.</p>}
    {!!e.coincidencias_ambiguas_excluidas?.length && <p className="rounded border border-amber-200 bg-amber-50 p-2">{e.coincidencias_ambiguas_excluidas.length} candidatos excluidos por ambigüedad; no se muestran como coincidencias confirmadas.</p>}
  </div>
  return <p className="text-xs">No hay una ficha disponible para esta regla.</p>
}

function FraudAlertRow({ alert, onUpdate, loading }) {
  const [notes, setNotes] = useState(alert.notas_revision || '')
  const save = (estado = alert.estado) => onUpdate({
    id: alert.id, data: { estado, notas: notes || null },
  })
  return (
    <div className="p-4 space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant={alert.prioridad === 'alta' ? 'error' : alert.prioridad === 'media' ? 'warning' : 'default'}>{alert.prioridad}</Badge>
            <Badge variant={alert.activa ? 'success' : 'default'}>{alert.activa ? 'Activa' : 'Histórica'}</Badge>
            <span className="font-display text-sm font-semibold">{{ autocompra: 'F05 · Autocompra', inventario_atipico: 'F06 · Inventario atípico', coincidencia_cantidad: 'F07 · Coincidencia exacta' }[alert.tipo] || alert.tipo.replaceAll('_', ' ')}</span>
            <span className="font-mono text-xs text-[var(--color-text-muted)]">oferta #{alert.oferta_id || '—'} · {alert.vendedor_nombre || `vendedor #${alert.vendedor_id || '—'}`}</span>
          </div>
          <p className="mt-1 text-xs text-[var(--color-text-secondary)]">
            {alert.producto_nombre || alert.producto_ref || 'Producto sin nombre'}{alert.oferta_sku ? ` · SKU ${alert.oferta_sku}` : ''}{alert.usuario_nombre ? ` · comprador ${alert.usuario_nombre}` : ''}
          </p>
          <ul className="mt-2 text-xs text-[var(--color-text-secondary)] space-y-1 list-disc pl-4">
            {(alert.motivos || []).map((motivo, i) => <li key={i}>{motivo}</li>)}
          </ul>
          <p className="mt-2 text-[11px] text-[var(--color-text-muted)]">
            Última detección: {formatDate(alert.ultima_deteccion)} · Origen: {alert.origen || 'anterior a la automatización'}
          </p>
        </div>
        <Select value={alert.estado} disabled={loading} onValueChange={save}>
          <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="pendiente">Pendiente</SelectItem>
            <SelectItem value="en_revision">En revisión</SelectItem>
            <SelectItem value="descartada">Descartada</SelectItem>
            <SelectItem value="revisada">Revisada</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <details className="text-xs rounded border border-[var(--color-border)] p-3">
        <summary className="cursor-pointer font-semibold">Abrir expediente y evidencia</summary>
        <div className="mt-3"><FraudEvidence alert={alert} /></div>
      </details>
      <p className="text-[11px] text-[var(--color-text-muted)]">Vigencia: {alert.activa ? 'activa en el último análisis' : 'histórica, no activa en la última evaluación'} · Revisión humana: {alert.estado?.replaceAll('_', ' ')}. Las notas y decisiones se conservan por separado.</p>
      <div className="flex gap-2 items-end">
        <div className="flex-1">
          <Label className="text-xs">Notas de revisión</Label>
          <Input value={notes} onChange={e => setNotes(e.target.value)} placeholder="Conclusiones del administrador" />
        </div>
        <Button variant="secondary" size="sm" loading={loading} onClick={() => save()}>Guardar notas</Button>
      </div>
    </div>
  )
}

function FraudIndicatorEvidence({ item, rule, onModerate, moderationPending }) {
  if (rule === 'bombardeo' || rule === 'reviewer_unico_vendedor') return <article className="rounded border border-[var(--color-border)] p-3 text-sm space-y-2">
    <h4 className="font-semibold">{rule === 'bombardeo' ? fraudValue(item.producto_nombre || item.producto_ref) : `${fraudValue(item.usuario_nombre)} → ${fraudValue(item.vendedor_nombre)}`}</h4>
    <p className="text-xs">{fraudValue(item.total_resenas)} reseñas · {rule === 'bombardeo' ? 'últimas 24 horas' : 'una sola tienda'}</p>
    <details><summary className="cursor-pointer text-xs font-semibold">Ver todas las reseñas ({item.resenas?.length ?? 0})</summary><div className="mt-2 max-h-96 overflow-y-auto space-y-2">{(item.resenas || []).map((r, i) => <FraudReviewCard key={`${r.resena_id}-${i}`} review={r} productName={rule === 'reviewer_unico_vendedor' ? fraudValue(r.producto_nombre || r.producto_ref) : undefined} />)}</div></details>
  </article>
  if (rule === 'cluster') return <article className="rounded border border-[var(--color-border)] p-3 text-sm space-y-2">
    <h4 className="font-semibold">{fraudValue(item.usuario1_nombre)} ↔ {fraudValue(item.usuario2_nombre)}</h4>
    <p className="text-xs">{fraudValue(item.productos_comunes)} productos reseñados en común · unidad de detección: par de usuarios</p>
    <details><summary className="cursor-pointer text-xs font-semibold">Comparar reseñas por producto</summary><div className="mt-2 max-h-[28rem] overflow-y-auto space-y-3">{(item.productos || []).map(product => <section key={product.ref} className="rounded border p-2"><h5 className="font-semibold mb-2">{fraudValue(product.nombre || product.ref)}</h5>{(product.resenas || []).map((pair, i) => <div key={`${pair.resena1_id}-${pair.resena2_id}-${i}`} className="grid md:grid-cols-2 gap-2 mb-2"><FraudReviewCard review={{ ...pair.resena1_detalle, resena_id: pair.resena1_id, usuario_nombre: pair.resena1_detalle?.usuario_nombre || item.usuario1_nombre, fecha: pair.resena1_detalle?.fecha || pair.resena1_fecha }} /><FraudReviewCard review={{ ...pair.resena2_detalle, resena_id: pair.resena2_id, usuario_nombre: pair.resena2_detalle?.usuario_nombre || item.usuario2_nombre, fecha: pair.resena2_detalle?.fecha || pair.resena2_fecha }} /></div>)}</section>)}</div></details>
  </article>
  return <article className="rounded border border-[var(--color-border)] p-3 text-sm space-y-2">
    <h4 className="font-semibold">{fraudValue(item.producto_nombre || item.producto_ref)}</h4>
    <p><strong>Cliente:</strong> {fraudValue(item.usuario_nombre)} · <strong>Vendedor:</strong> {fraudValue(item.vendedor_nombre)}</p>
    <FraudReviewCard review={{ ...item, usuario_nombre: item.usuario_nombre }} />
    <p className="text-xs"><strong>Motivo:</strong> {fraudValue(item.motivo_no_verificada)}</p>
    <p className="text-xs"><strong>Evidencia disponible:</strong> reseña #{fraudValue(item.resena_id)}{item.evidencia_disponible?.pedido_linea_id ? ` · línea #${item.evidencia_disponible.pedido_linea_id}` : ''}. <strong>Evidencia faltante:</strong> {fraudValue(item.evidencia_faltante)}</p>
    <p className="rounded border border-amber-200 bg-amber-50 p-2 text-xs">No se encontró respaldo suficiente de una compra pagada válida. Esto no demuestra que la compra nunca haya ocurrido.</p>
    <div className="flex gap-3"><button className="text-xs font-semibold text-emerald-600" disabled={moderationPending} onClick={() => onModerate(item.resena_id, 'aprobada')}><CheckCircle size={13} className="inline" /> Aprobar moderación</button><button className="text-xs font-semibold text-red-600" disabled={moderationPending} onClick={() => onModerate(item.resena_id, 'rechazada')}><XCircle size={13} className="inline" /> Rechazar</button></div>
  </article>
}

// ── FraudSection ──
function FraudSection() {
  const qc = useQueryClient()
  const [indicator, setIndicator] = useState(null)
  const [indicatorPage, setIndicatorPage] = useState(1)
  const [indicatorSize, setIndicatorSize] = useState(20)
  const [indicatorSearch, setIndicatorSearch] = useState('')
  const [alertPage, setAlertPage] = useState(1)
  const [alertSize, setAlertSize] = useState(20)
  const [alertSearch, setAlertSearch] = useState('')
  const [alertType, setAlertType] = useState('todos')
  const [alertPriority, setAlertPriority] = useState('todas')
  const [alertState, setAlertState] = useState('todos')
  const [alertActive, setAlertActive] = useState('todas')
  const [alertOrder, setAlertOrder] = useState('fecha_desc')

  const { data: fraudData, isLoading: fraudLoading } = useQuery({
    queryKey: ['fraud-summary'],
    queryFn: () => getFraudSummary().then(r => r.data),
  })

  const indicatorRule = indicator?.rule || indicator?.key?.replace('_historico', '')
  const indicatorSegment = indicator?.key?.endsWith('_historico')
    ? 'historicas_no_verificadas' : 'verificadas_publicas'
  const { data: indicatorData, isLoading: indicatorLoading, isPlaceholderData: indicatorPlaceholder, isError: indicatorError } = useQuery({
    queryKey: ['fraud-indicator', indicatorRule, indicatorSegment, indicatorPage, indicatorSize, indicatorSearch],
    queryFn: () => getFraudIndicator(indicatorRule, {
      pagina: indicatorPage, tamano: indicatorSize, buscar: indicatorSearch || undefined,
      segmento: indicatorSegment,
    }).then(r => r.data),
    enabled: Boolean(indicatorRule),
    placeholderData: keepPreviousData,
  })

  const alertParams = {
    pagina: alertPage, tamano: alertSize, buscar: alertSearch || undefined,
    tipo: alertType === 'todos' ? undefined : alertType,
    prioridad: alertPriority === 'todas' ? undefined : alertPriority,
    estado: alertState === 'todos' ? undefined : alertState,
    activa: alertActive === 'todas' ? undefined : alertActive === 'activas',
    orden: alertOrder,
  }
  const { data: alertsData, isLoading: alertsLoading, isPlaceholderData: alertsPlaceholder, isError: alertsError } = useQuery({
    queryKey: ['fraud-alerts', alertParams],
    queryFn: () => getFraudAlertsPaginated(alertParams).then(r => r.data),
    placeholderData: keepPreviousData,
  })
  const alerts = alertsData?.items || []

  const { data: analysisStatus, isLoading: analysisLoading } = useQuery({
    queryKey: ['fraud-analysis-status'],
    queryFn: () => getFraudAnalysisStatus().then(r => r.data),
    refetchInterval: 30000,
  })

  const recalculateMutation = useMutation({
    mutationFn: recalculateFraudAlerts,
    onSuccess: (res) => {
      const summary = res.data?.resumen || {}
      toast.success(`Análisis actualizado: ${summary.autocompras ?? 0} F05, ${summary.inventario_atipico ?? 0} F06 y ${summary.coincidencia_cantidad ?? 0} F07.`)
      qc.invalidateQueries({ queryKey: ['fraud-alerts'] })
      qc.invalidateQueries({ queryKey: ['fraud-summary'] })
      qc.invalidateQueries({ queryKey: ['fraud-analysis-status'] })
    },
    onError: (error) => toast.error(error?.response?.status === 409
      ? 'Ya hay un análisis de fraude en curso.'
      : 'No se pudo recalcular las señales.'),
  })

  const alertMutation = useMutation({
    mutationFn: ({ id, data }) => updateFraudAlert(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['fraud-alerts'] }),
    onError: () => toast.error('No se pudo actualizar la alerta.'),
  })

  const moderateMutation = useMutation({
    mutationFn: ({ resenaId, estado }) => moderateReview(resenaId, estado),
    onSuccess: (_, variables) => {
      toast.success(variables.estado === 'aprobada'
        ? 'Moderación aprobada. La reseña seguirá oculta mientras su compra no pueda verificarse.'
        : 'Estado de reseña actualizado.')
      qc.invalidateQueries({ queryKey: ['fraud-indicator'] })
      qc.invalidateQueries({ queryKey: ['fraud-summary'] })
    },
    onError: () => toast.error('No se pudo actualizar la reseña.'),
  })

  const FRAUD_CARDS = [
    { key: 'bombardeo',             rule: 'bombardeo', label: 'F01 · Bombardeo', color: 'text-red-600 bg-red-50 border-red-200' },
    { key: 'sin_compra_verificada', rule: 'sin_compra', label: 'F04 · Compra no verificable', color: 'text-amber-600 bg-amber-50 border-amber-200' },
    { key: 'reviewer_unico_vendedor', rule: 'reviewer_unico_vendedor', label: 'F02 · Un vendedor', color: 'text-orange-600 bg-orange-50 border-orange-200' },
    { key: 'cluster_coordinado',    rule: 'cluster', label: 'F03 · Cluster coordinado', color: 'text-purple-600 bg-purple-50 border-purple-200' },
    { key: 'bombardeo_historico', rule: 'bombardeo', label: 'F01 · Reseñas históricas no verificadas', color: 'text-slate-600 bg-slate-50 border-slate-200' },
    { key: 'reviewer_unico_vendedor_historico', rule: 'reviewer_unico_vendedor', label: 'F02 · Reseñas históricas no verificadas', color: 'text-slate-600 bg-slate-50 border-slate-200' },
    { key: 'cluster_coordinado_historico', rule: 'cluster', label: 'F03 · Reseñas históricas no verificadas', color: 'text-slate-600 bg-slate-50 border-slate-200' },
    { key: 'autocompra', commercialType: 'autocompra', label: 'F05 · Autocompra', color: 'text-rose-600 bg-rose-50 border-rose-200' },
    { key: 'inventario_atipico', commercialType: 'inventario_atipico', label: 'F06 · Inventario', color: 'text-blue-600 bg-blue-50 border-blue-200' },
    { key: 'coincidencia_cantidad', commercialType: 'coincidencia_cantidad', label: 'F07 · Coincidencia', color: 'text-emerald-700 bg-emerald-50 border-emerald-200' },
  ]

  const runLabel = (run) => run
    ? `${run.estado} · ${formatDate(run.finalizada_en || run.iniciada_en)} · ${run.duracion_ms ?? 0} ms`
    : 'Sin ejecuciones'

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          ['Última automática', analysisStatus?.ultima_automatica],
          ['Última manual', analysisStatus?.ultima_manual],
          ['Último análisis exitoso', analysisStatus?.ultimo_exito],
        ].map(([label, run]) => (
          <div key={label} className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
            <p className="text-xs uppercase font-bold text-[var(--color-text-muted)]">{label}</p>
            {analysisLoading ? <Skeleton className="h-5 mt-2" /> : <p className="text-sm mt-2">{runLabel(run)}</p>}
            {run?.error && <p className="text-xs text-red-600 mt-1">{run.error}</p>}
          </div>
        ))}
      </div>
      {analysisStatus?.en_curso && (
        <div className="rounded border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          Hay un análisis en curso desde {formatDate(analysisStatus.en_curso.iniciada_en)}.
        </div>
      )}
      {/* Tarjetas de resumen */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {FRAUD_CARDS.map((card) => {
          const { key, label, color } = card
          const item = fraudData?.[key]
          return (
            <button key={key} type="button" onClick={() => { if (card.commercialType) { setAlertType(card.commercialType); setAlertPage(1); document.getElementById('fraud-commercial-alerts')?.scrollIntoView({ behavior: 'smooth' }) } else { setIndicator(card); setIndicatorPage(1); setIndicatorSearch('') } }} className={`rounded-[var(--radius-lg)] border p-4 text-left transition hover:-translate-y-0.5 hover:shadow-sm ${color}`}>
              <div className="flex items-center gap-2 mb-1">
                <AlertTriangle size={15} />
                <span className="font-sans text-xs font-bold uppercase tracking-wide">{label}</span>
              </div>
              {fraudLoading
                ? <Skeleton className="h-8 w-16 mt-1" />
                : <p className="font-mono font-bold text-3xl">{item?.count ?? 0}</p>
              }
              <p className="mt-2 text-[11px] font-semibold">Ver registros →</p>
            </button>
          )
        })}
      </div>

      <div id="fraud-commercial-alerts" className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
        <div className="px-5 py-4 border-b border-[var(--color-border)] flex items-center justify-between gap-4">
          <div>
            <h3 className="font-display font-semibold text-base">Alertas comerciales explicables</h3>
            <p className="font-sans text-xs text-[var(--color-text-muted)] mt-0.5">
              Indicios de autocompras e inventario atípico; requieren revisión humana y no bloquean cuentas.
            </p>
          </div>
          <Button size="sm" disabled={Boolean(analysisStatus?.en_curso)} loading={recalculateMutation.isPending} onClick={() => recalculateMutation.mutate()}>
            Recalcular señales
          </Button>
        </div>
        <div className="p-4 border-b border-[var(--color-border)] grid grid-cols-1 md:grid-cols-7 gap-2">
          <Input className="md:col-span-2" value={alertSearch} onChange={e => { setAlertSearch(e.target.value); setAlertPage(1) }} placeholder="Buscar vendedor, producto, SKU u oferta" />
          <Select value={alertType} onValueChange={v => { setAlertType(v); setAlertPage(1) }}><SelectTrigger><SelectValue placeholder="Tipo" /></SelectTrigger><SelectContent>
            <SelectItem value="todos">F05–F07</SelectItem><SelectItem value="autocompra">F05 · Autocompra</SelectItem><SelectItem value="inventario_atipico">F06 · Inventario</SelectItem><SelectItem value="coincidencia_cantidad">F07 · Coincidencia</SelectItem>
          </SelectContent></Select>
          <Select value={alertPriority} onValueChange={v => { setAlertPriority(v); setAlertPage(1) }}><SelectTrigger><SelectValue placeholder="Prioridad" /></SelectTrigger><SelectContent>
            <SelectItem value="todas">Toda prioridad</SelectItem>{['informativa','baja','media','alta'].map(v => <SelectItem key={v} value={v}>{v}</SelectItem>)}
          </SelectContent></Select>
          <Select value={alertState} onValueChange={v => { setAlertState(v); setAlertPage(1) }}><SelectTrigger><SelectValue placeholder="Revisión" /></SelectTrigger><SelectContent>
            <SelectItem value="todos">Todo estado</SelectItem><SelectItem value="pendiente">Pendiente</SelectItem><SelectItem value="en_revision">En revisión</SelectItem><SelectItem value="descartada">Descartada</SelectItem><SelectItem value="revisada">Revisada</SelectItem>
          </SelectContent></Select>
          <Select value={alertActive} onValueChange={v => { setAlertActive(v); setAlertPage(1) }}><SelectTrigger><SelectValue placeholder="Vigencia" /></SelectTrigger><SelectContent>
            <SelectItem value="todas">Activas e históricas</SelectItem><SelectItem value="activas">Activas</SelectItem><SelectItem value="historicas">Históricas</SelectItem>
          </SelectContent></Select>
          <Select value={alertOrder} onValueChange={v => { setAlertOrder(v); setAlertPage(1) }}><SelectTrigger><SelectValue placeholder="Orden" /></SelectTrigger><SelectContent><SelectItem value="fecha_desc">Más recientes</SelectItem><SelectItem value="prioridad_desc">Mayor prioridad</SelectItem></SelectContent></Select>
        </div>
        <div className="divide-y divide-[var(--color-border)]">
          {alertsLoading || alertsPlaceholder
            ? <div className="p-5"><Skeleton className="h-16 w-full" /></div>
            : alertsError
              ? <p className="p-8 text-center text-sm text-red-600">No fue posible consultar los expedientes. Intenta nuevamente.</p>
            : alerts.length === 0
              ? <p className="p-8 text-center text-sm text-[var(--color-text-muted)]">
                  {analysisStatus?.ultimo_exito
                    ? 'No se detectaron alertas comerciales.'
                    : 'Aún no se ha ejecutado un análisis comercial.'}
                </p>
              : alerts.map(alert => <FraudAlertRow
                  key={alert.id}
                  alert={alert}
                  loading={alertMutation.isPending}
                  onUpdate={(payload) => alertMutation.mutate(payload)}
                />)}
        </div>
        <div className="p-4 border-t border-[var(--color-border)] flex items-center justify-between gap-3">
          <span className="text-xs text-[var(--color-text-muted)]">{alertsData?.total || 0} expedientes · página {alertsData?.pagina || 1} de {alertsData?.paginas || 1}</span>
          <div className="flex items-center gap-2">
            <Select value={String(alertSize)} onValueChange={v => { setAlertSize(Number(v)); setAlertPage(1) }}><SelectTrigger className="w-20"><SelectValue /></SelectTrigger><SelectContent>{[10,20,50].map(v => <SelectItem key={v} value={String(v)}>{v}</SelectItem>)}</SelectContent></Select>
            <Button variant="secondary" size="sm" disabled={alertPage <= 1} onClick={() => setAlertPage(p => p - 1)}>Anterior</Button>
            <Button variant="secondary" size="sm" disabled={alertPage >= (alertsData?.paginas || 1)} onClick={() => setAlertPage(p => p + 1)}>Siguiente</Button>
          </div>
        </div>
      </div>

      <Dialog open={Boolean(indicator)} onOpenChange={open => !open && setIndicator(null)}>
        <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
          <DialogTitle>{indicator?.label || 'Detalle del indicador'}</DialogTitle>
          <DialogDescription>
            {indicatorRule === 'sin_compra'
              ? 'Reseñas autoritativas consultadas en MySQL; Neo4j aporta únicamente el nombre proyectado del producto.'
              : 'Patrones consultados en Neo4j y reseñas completadas desde MySQL. Son señales para investigar; no bloquean operaciones.'}
          </DialogDescription>
          <FraudGuide type={indicatorRule} segment={indicatorSegment} />
          {indicatorRule === 'bombardeo' && (
            <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
              Ventana analizada: últimas 24 horas · umbral: 5 reseñas {indicatorSegment === 'historicas_no_verificadas' ? 'históricas no verificadas' : 'verificadas y aprobadas'} por producto.
            </p>
          )}
          <div className="flex gap-2">
            <Input value={indicatorSearch} onChange={e => { setIndicatorSearch(e.target.value); setIndicatorPage(1) }} placeholder="Buscar usuario, producto o vendedor" />
            <Select value={String(indicatorSize)} onValueChange={v => { setIndicatorSize(Number(v)); setIndicatorPage(1) }}><SelectTrigger className="w-24"><SelectValue /></SelectTrigger><SelectContent>{[10,20,50].map(v => <SelectItem key={v} value={String(v)}>{v}</SelectItem>)}</SelectContent></Select>
          </div>
          {indicatorLoading || indicatorPlaceholder ? <Skeleton className="h-52 w-full" /> : indicatorError ? <p className="py-10 text-center text-sm text-red-600">No fue posible consultar este indicador.</p> : (
            <div className="space-y-2">
              {(indicatorData?.items || []).map((item, index) => <FraudIndicatorEvidence
                key={item.resena_id || `${item.usuario_id || item.usuario1_id || item.producto_ref}-${index}`}
                item={item} rule={indicatorRule} moderationPending={moderateMutation.isPending}
                onModerate={(resenaId, estado) => moderateMutation.mutate({ resenaId, estado })}
              />)}
              {!indicatorData?.items?.length && <p className="py-10 text-center text-sm text-[var(--color-text-muted)]">{indicatorRule === 'reviewer_unico_vendedor' ? 'No se detectaron usuarios que cumplan este patrón.' : 'No se detectaron casos para estos filtros.'}</p>}
            </div>
          )}
          <div className="flex justify-between items-center"><span className="text-xs text-[var(--color-text-muted)]">{indicatorData?.total || 0} registros · página {indicatorData?.pagina || 1} de {indicatorData?.paginas || 1}</span><div className="flex gap-2"><Button variant="secondary" size="sm" disabled={indicatorPage <= 1} onClick={() => setIndicatorPage(p => p - 1)}>Anterior</Button><Button variant="secondary" size="sm" disabled={indicatorPage >= (indicatorData?.paginas || 1)} onClick={() => setIndicatorPage(p => p + 1)}>Siguiente</Button><DialogClose asChild><Button variant="secondary" size="sm">Cerrar</Button></DialogClose></div></div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── AdminPage ──
// Panel de administrador: estadísticas con gráficas, CRUD de productos y categorías, gestión de usuarios/roles/pedidos/ventas y solicitudes de catálogo
export default function AdminPage() {
  const [params, setParams] = useSearchParams()
  const activeSection = params.get('section') || 'stats'
  const setActiveSection = section => setParams({section})

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <div className="flex">
        <aside className="w-56 shrink-0 min-h-screen border-r border-[var(--color-border)] bg-[var(--color-surface)] pt-8">
          <div className="px-5 mb-6">
            <h1 className="font-display font-bold text-base text-[var(--color-text-primary)]">Panel Admin</h1>
            <p className="font-sans text-xs text-[var(--color-text-muted)] mt-0.5">TiendaYa</p>
          </div>
          <Separator />
          <nav className="p-3 mt-2 space-y-1">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon
              return (
                <button key={item.id} onClick={() => setActiveSection(item.id)}
                  className={cn('w-full flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-md)] text-sm font-sans font-medium transition-colors text-left',
                    activeSection === item.id ? 'bg-[var(--color-action)] text-white' : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] hover:text-[var(--color-text-primary)]')}>
                  <Icon size={16} />
                  {item.label}
                </button>
              )
            })}
          </nav>
        </aside>

        <main className="flex-1 min-w-0 p-8">
          <h2 className="font-display font-bold text-2xl text-[var(--color-text-primary)] mb-6">
            {NAV_ITEMS.find((n) => n.id === activeSection)?.label}
          </h2>
          {activeSection === 'stats'      && <StatsSection />}
          {activeSection === 'analytics'  && <AnalyticsSection />}
          {activeSection === 'products'   && <ProductsSection />}
          {activeSection === 'categories' && <CategoriesSection />}
          {activeSection === 'users'      && <UsersSection />}
          {activeSection === 'vendors'    && <AdminVendorsSection />}
          {activeSection === 'orders'     && <OrdersSection />}
          {activeSection === 'sales'      && <SalesSection />}
          {activeSection === 'requests'   && <AdminCatalogRequestsSection />}
          {activeSection === 'fraud'      && <FraudSection />}
          {activeSection === 'sync'       && <SyncHealthSection />}
        </main>
      </div>
    </div>
  )
}
