import React, { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueries, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, PieChart, Pie, Cell, Legend,
} from 'recharts'
import {
  BarChart2, Package, History, Users, ShieldCheck, ShoppingBag, User,
  Plus, Edit, Trash2, FolderTree, X as XIcon, ImagePlus, Image as ImageIcon, Search,
  TrendingUp, FileSpreadsheet, ChevronDown, ChevronRight, ClipboardList, Store, Layers,
  Inbox,
} from 'lucide-react'
import { toast } from 'sonner'
import { getCatalogStats, getProducts, getCategories, getCategorySchema, createProduct, updateProduct, deleteProduct } from '../api/products'
import { getAdminUsers, updateUserRoles, getAdminCategories, createCategory, updateCategorySchema, deleteCategory, uploadAdminImage, getAdminVendors, getAdminSalesStats, getAdminSales, exportAdminSalesExcel, getAdminOrders, updateAdminOrderStatus, setVendorProfile, getProductOffers, addProductOffer, updateProductOffer } from '../api/admin'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../components/ui/select'
import { Dialog, DialogContent, DialogTitle, DialogDescription, DialogClose } from '../components/ui/dialog'
import { Skeleton } from '../components/ui/skeleton'
import { Separator } from '../components/ui/separator'
import { formatQ, formatDate, cn } from '../lib/utils'
import { AdminCatalogRequestsSection } from '../components/admin/CatalogRequestsSection'

const NAV_ITEMS = [
  { id: 'stats',      label: 'Estadísticas', icon: BarChart2      },
  { id: 'products',   label: 'Productos',    icon: Package        },
  { id: 'categories', label: 'Categorías',   icon: FolderTree     },
  { id: 'users',      label: 'Usuarios',     icon: Users          },
  { id: 'orders',     label: 'Pedidos',      icon: ClipboardList  },
  { id: 'sales',      label: 'Ventas',       icon: TrendingUp     },
  { id: 'requests',   label: 'Solicitudes',  icon: Inbox          },
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
function AttrRow({ attr, onChange, onRemove }) {
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
function ImageManager({ images, onChange }) {
  const fileRef = useRef(null)
  const [uploading, setUploading] = useState(false)

  async function handleFileChange(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const res = await uploadAdminImage(file)
      onChange([...images, res.data.url])
      toast.success('Imagen subida correctamente.')
    } catch {
      toast.error('Error al subir la imagen.')
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  function remove(idx) {
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
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard label="Total de productos" value={global.total_productos ?? '—'} />
        <StatCard label="Disponibles" value={global.total_disponibles ?? '—'} sub={global.total_productos ? `${Math.round((global.total_disponibles / global.total_productos) * 100)}% del catálogo` : undefined} />
        <StatCard label="Precio promedio global" value={global.precio_promedio_global ? formatQ(global.precio_promedio_global) : '—'} />
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
function ProductFormModal({ open, onOpenChange, product }) {
  const isEdit = !!product
  const queryClient = useQueryClient()

  const EMPTY = { nombre: '', descripcion: '', precio: '', categoria_slugs: [], disponible: true, estado: 'activo', atributos: {}, stock: '', imagenes: [], vendedor_usuario_id: '' }
  const [form, setForm] = useState(EMPTY)

  useEffect(() => {
    if (open) {
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
      onOpenChange(false)
    },
    onError: (err) => {
      const detail = err?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Error al guardar el producto.')
    },
  })

  function set(key, value) { setForm((p) => ({ ...p, [key]: value })) }
  function setAttr(key, value) { setForm((p) => ({ ...p, atributos: { ...p.atributos, [key]: value } })) }

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
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
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

// ── ProductsSection ──
// ── OffersModal ──
function OffersModal({ product, open, onOpenChange }) {
  const queryClient = useQueryClient()
  const [newVendorId, setNewVendorId] = useState('')
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

  const { data: vendorsData = [] } = useQuery({
    queryKey: ['admin-vendors'],
    queryFn: () => getAdminVendors().then((r) => r.data),
    enabled: open,
  })

  const existingVendorIds = new Set(offers.filter(o => o.estado !== 'descontinuada').map(o => o.vendedor_id))
  const availableVendors = vendorsData.filter(
    v => v.vendedor_id && !existingVendorIds.has(v.vendedor_id)
  )

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['product-offers', product?._id] })
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
    addMutation.mutate({ vendedor_id: Number(newVendorId), precio: Number(newPrecio), stock: Number(newStock) })
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogTitle className="flex items-center gap-2">
          <Layers size={16} /> Ofertas — {product?.nombre}
        </DialogTitle>
        <DialogDescription>
          Cada oferta pertenece a un vendedor distinto con su propio precio e inventario.
        </DialogDescription>

        {isLoading ? (
          <div className="space-y-2">{[1,2].map(i => <Skeleton key={i} className="h-12 w-full" />)}</div>
        ) : (
          <div className="overflow-hidden rounded-[var(--radius-md)] border border-[var(--color-border)]">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-[var(--color-background)]">
                  {['Vendedor', 'SKU', 'Precio', 'Stock', 'Estado', ''].map(h => (
                    <th key={h} className="px-3 py-2 text-left font-sans font-semibold text-xs uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)]">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {offers.length === 0 && (
                  <tr><td colSpan={6} className="px-3 py-6 text-center font-sans text-sm text-[var(--color-text-muted)]">Sin ofertas registradas</td></tr>
                )}
                {offers.map((offer) => (
                  <tr key={offer.oferta_id} className="border-b border-[var(--color-border)] last:border-0">
                    <td className="px-3 py-2 font-sans font-semibold text-[var(--color-text-primary)]">{offer.vendedor_nombre}</td>
                    <td className="px-3 py-2 font-mono text-xs text-[var(--color-text-muted)]">{offer.sku}</td>
                    <td className="px-3 py-2">
                      {editingId === offer.oferta_id ? (
                        <Input type="number" value={editPrecio} onChange={e => setEditPrecio(e.target.value)} className="w-24 h-7 text-xs font-mono" step="0.01" min="0" />
                      ) : (
                        <span className="font-mono font-semibold">{formatQ(offer.precio)}</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {editingId === offer.oferta_id ? (
                        <Input type="number" value={editStock} onChange={e => setEditStock(e.target.value)} className="w-20 h-7 text-xs font-mono" min="0" />
                      ) : (
                        <span className={`font-mono ${offer.stock === 0 ? 'text-[var(--color-error)]' : offer.stock <= 5 ? 'text-amber-500' : 'text-[var(--color-text-primary)]'}`}>{offer.stock}</span>
                      )}
                    </td>
                    <td className="px-3 py-2"><Badge variant={estadoBadge[offer.estado] || 'secondary'}>{offer.estado}</Badge></td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1">
                        {editingId === offer.oferta_id ? (
                          <>
                            <Button size="sm" variant="ghost" onClick={() => handleSaveEdit(offer)} disabled={updateMutation.isPending}>Guardar</Button>
                            <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>Cancelar</Button>
                          </>
                        ) : (
                          <>
                            <Button size="sm" variant="ghost" onClick={() => startEdit(offer)}><Edit size={12} /></Button>
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
        )}

        {availableVendors.length > 0 && (
          <form onSubmit={handleAdd} className="border border-[var(--color-border)] rounded-[var(--radius-md)] p-4 space-y-3 bg-[var(--color-background)]">
            <p className="font-sans text-sm font-semibold text-[var(--color-text-primary)]">Añadir oferta de otro vendedor</p>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label className="text-xs">Vendedor *</Label>
                <Select value={newVendorId} onValueChange={setNewVendorId}>
                  <SelectTrigger className="h-8 text-xs mt-1">
                    <SelectValue placeholder="Seleccionar..." />
                  </SelectTrigger>
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
              <Button type="submit" size="sm" loading={addMutation.isPending} disabled={!newVendorId}><Plus size={13} /> Añadir oferta</Button>
            </div>
          </form>
        )}

        {availableVendors.length === 0 && offers.length > 0 && (
          <p className="font-sans text-xs text-[var(--color-text-muted)] text-center py-2">Todos los vendedores registrados ya tienen una oferta para este producto.</p>
        )}

        <div className="flex justify-end pt-1">
          <DialogClose asChild><Button variant="secondary" size="sm">Cerrar</Button></DialogClose>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function ProductsSection() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [editProduct, setEditProduct] = useState(null)
  const [offersOpen, setOffersOpen] = useState(false)
  const [offersProduct, setOffersProduct] = useState(null)
  const PAGE_SIZE = 15
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['admin-products', page, search],
    queryFn: () => getProducts({ page, page_size: PAGE_SIZE, ...(search && { q: search }) }).then((r) => r.data),
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
      toast.success('Producto eliminado.')
      queryClient.invalidateQueries({ queryKey: ['admin-products'] })
      queryClient.invalidateQueries({ queryKey: ['products'] })
    },
    onError: () => toast.error('No se pudo eliminar el producto.'),
  })

  function openCreate() { setEditProduct(null); setModalOpen(true) }
  function openEdit(prod) { setEditProduct(prod); setModalOpen(true) }
  function handleDelete(prod) {
    if (!window.confirm(`¿Eliminar "${prod.nombre}"? Esta acción no se puede deshacer.`)) return
    deleteMutation.mutate(prod._id)
  }

  const products = data?.items || []
  const totalPages = data?.total_pages || 1

  if (isLoading) return (
    <div className="space-y-3">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
  )

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
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
        <div className="ml-auto">
          <Button size="sm" onClick={openCreate}><Plus size={14} /> Nuevo producto</Button>
        </div>
      </div>

      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[var(--color-background)]">
                {['Imagen', 'Nombre', 'Categoría', 'Precio', 'Stock', 'Disponible', 'Acciones'].map((h) => (
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
                      <span className="line-clamp-1">{prod.nombre}</span>
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
                      <Badge variant={prod.disponible ? 'success' : 'error'}>{prod.disponible ? 'Sí' : 'No'}</Badge>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" size="sm" onClick={() => openEdit(prod)}><Edit size={13} /> Editar</Button>
                        <Button variant="ghost" size="sm" onClick={() => { setOffersProduct(prod); setOffersOpen(true) }}>
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

      <ProductFormModal open={modalOpen} onOpenChange={setModalOpen} product={editProduct} />
      <OffersModal open={offersOpen} onOpenChange={setOffersOpen} product={offersProduct} />
    </div>
  )
}

// ── CategoriesSection ──
function CategoriesSection() {
  const queryClient = useQueryClient()

  const [createOpen, setCreateOpen] = useState(false)
  const [editTarget, setEditTarget] = useState(null)
  const [editOpen, setEditOpen] = useState(false)

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
    onError: (err) => toast.error(err?.response?.data?.detail || 'Error al crear categoría.'),
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

  function openEdit(cat) {
    setEditTarget(cat)
    setEditAttrs(cat.atributos.length ? cat.atributos.map((a) => ({ ...a })) : [])
    setEditSkuPrefix(cat.sku_prefix || '')
    setEditOpen(true)
  }

  function handleDelete(cat) {
    if (!window.confirm(`¿Eliminar categoría "${cat.nombre}"? Esto también eliminará su esquema de campos.`)) return
    deleteMut.mutate(cat.slug)
  }

  if (isLoading) return (
    <div className="space-y-3">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
  )

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setCreateOpen(true)}><Plus size={14} /> Nueva categoría</Button>
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
            {cats.map((cat, idx) => (
              <tr key={cat.id} className={cn('border-b border-[var(--color-border)] last:border-0', idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]')}>
                <td className="px-4 py-3 font-display font-semibold text-[var(--color-text-primary)]">
                  {cat.nombre}
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
            {cats.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-8 text-center font-sans text-sm text-[var(--color-text-muted)]">No hay categorías todavía.</td></tr>
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
                {['Pedido #', 'Fecha', 'Comprador', 'Total', 'Estado actual', 'Cambiar estado'].map((h) => (
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
                        <td className="px-4 py-3 font-mono font-semibold text-[var(--color-text-primary)]">#{p.id}</td>
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
                          <Select
                            value={p.estado}
                            onValueChange={(v) => handleStatusChange(p.id, v)}
                            disabled={updatingId === p.id}
                          >
                            <SelectTrigger className="h-8 text-xs">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="pendiente">Pendiente</SelectItem>
                              <SelectItem value="confirmado">Confirmado</SelectItem>
                              <SelectItem value="enviado">Enviado</SelectItem>
                              <SelectItem value="entregado">Entregado</SelectItem>
                              <SelectItem value="cancelado">Cancelado</SelectItem>
                              <SelectItem value="reembolsado">Reembolsado</SelectItem>
                            </SelectContent>
                          </Select>
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
  const [page, setPage] = useState(1)
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

  function toggleRole(user, role) {
    const current = new Set(user.roles)
    if (current.has(role)) current.delete(role)
    else current.add(role)
    mutation.mutate({ userId: user.id, roles: [...current] })
  }

  const users = data?.items || []
  const totalPages = data?.total_pages || 1

  if (isLoading) return (
    <div className="space-y-3">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-14 w-full" />)}</div>
  )

  return (
    <div>
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
              {users.map((user, idx) => (
                <tr key={user.id} className={cn('border-b border-[var(--color-border)] last:border-0', idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]')}>
                  <td className="px-4 py-3">
                    <p className="font-display font-semibold text-[var(--color-text-primary)]">{user.nombre} {user.apellido}</p>
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
                      <Button variant="ghost" size="sm" onClick={() => {
                        const vp = vendorByUserId[user.id]
                        setVpUser(user)
                        setVpNombre(vp?.nombre_comercial || '')
                        setVpNit(vp?.nit || '')
                        setVpOpen(true)
                      }}>
                        <Store size={13} /> Perfil vendedor
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
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
                            onClick={() => setExpandedId(isExpanded ? null : pedido.id)}
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

// ── AdminPage ──
export default function AdminPage() {
  const [activeSection, setActiveSection] = useState('stats')

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
          {activeSection === 'products'   && <ProductsSection />}
          {activeSection === 'categories' && <CategoriesSection />}
          {activeSection === 'users'      && <UsersSection />}
          {activeSection === 'orders'     && <OrdersSection />}
          {activeSection === 'sales'      && <SalesSection />}
          {activeSection === 'requests'   && <AdminCatalogRequestsSection />}
        </main>
      </div>
    </div>
  )
}
