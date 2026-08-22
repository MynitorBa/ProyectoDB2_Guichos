import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { BarChart2, Package, History, Users, ShieldCheck, ShoppingBag, User, Plus, Edit, Trash2, FolderTree, GripVertical, X as XIcon } from 'lucide-react'
import { toast } from 'sonner'
import { getCatalogStats, getProducts, getCategories, getCategorySchema, createProduct, updateProduct, deleteProduct } from '../api/products'
import { getAdminUsers, updateUserRoles, getAdminCategories, createCategory, updateCategorySchema, deleteCategory } from '../api/admin'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../components/ui/select'
import { Dialog, DialogContent, DialogTitle, DialogDescription, DialogClose } from '../components/ui/dialog'
import { Skeleton } from '../components/ui/skeleton'
import { Separator } from '../components/ui/separator'
import { formatQ } from '../lib/utils'
import { cn } from '../lib/utils'

const NAV_ITEMS = [
  { id: 'stats',      label: 'Estadísticas', icon: BarChart2  },
  { id: 'products',   label: 'Productos',    icon: Package    },
  { id: 'categories', label: 'Categorías',   icon: FolderTree },
  { id: 'users',      label: 'Usuarios',     icon: Users      },
]

const ROLE_META = {
  administrador: { label: 'Admin',    Icon: ShieldCheck,   active: 'bg-[var(--color-action)] text-white border-[var(--color-action)]',    inactive: 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-action)] hover:text-[var(--color-action)]' },
  vendedor:      { label: 'Vendedor', Icon: ShoppingBag,   active: 'bg-[var(--color-jade)] text-white border-[var(--color-jade)]',          inactive: 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-jade)] hover:text-[var(--color-jade)]' },
  comprador:     { label: 'Comprador', Icon: User,          active: 'bg-[var(--color-border-strong)] text-[var(--color-text-primary)] border-[var(--color-border-strong)]', inactive: 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-border-strong)] hover:text-[var(--color-text-primary)]' },
}
const ALL_ROLES = ['comprador', 'vendedor', 'administrador']

// Los campos de cada categoría vienen de MongoDB (categoria_esquemas), no hardcodeados aquí.
// El campo tiene: nombre (key), etiqueta (label), tipo (string|number|boolean), requerido, placeholder

function StatCard({ label, value, sub }) {
  return (
    <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5">
      <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-1">
        {label}
      </p>
      <p className="font-mono font-bold text-3xl text-[var(--color-text-primary)]">{value}</p>
      {sub && (
        <p className="font-sans text-xs text-[var(--color-text-muted)] mt-1">{sub}</p>
      )}
    </div>
  )
}

function StatsSection() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['catalog-stats'],
    queryFn: () => getCatalogStats().then((r) => r.data[0]),
  })

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }

  if (isError || !data) {
    return (
      <p className="font-sans text-sm text-[var(--color-error)]">
        Error al cargar estadísticas.
      </p>
    )
  }

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
        <StatCard
          label="Total de productos"
          value={global.total_productos ?? '—'}
        />
        <StatCard
          label="Disponibles"
          value={global.total_disponibles ?? '—'}
          sub={global.total_productos ? `${Math.round((global.total_disponibles / global.total_productos) * 100)}% del catálogo` : undefined}
        />
        <StatCard
          label="Precio promedio global"
          value={global.precio_promedio_global ? formatQ(global.precio_promedio_global) : '—'}
        />
      </div>

      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-5">
        <h3 className="font-display font-semibold text-base text-[var(--color-text-primary)] mb-4">
          Precio promedio por categoría
        </h3>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 11, fontFamily: 'var(--font-sans)', fill: 'var(--color-text-muted)' }}
            />
            <YAxis
              tick={{ fontSize: 11, fontFamily: 'var(--font-mono)', fill: 'var(--color-text-muted)' }}
              tickFormatter={(v) => `Q${v}`}
            />
            <Tooltip
              formatter={(v) => [formatQ(v), 'Precio promedio']}
              contentStyle={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-md)',
                fontFamily: 'var(--font-sans)',
                fontSize: 12,
              }}
            />
            <Bar dataKey="promedio" fill="var(--color-action)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {topProductos.length > 0 && (
        <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
          <div className="px-5 py-4 border-b border-[var(--color-border)]">
            <h3 className="font-display font-semibold text-base text-[var(--color-text-primary)]">
              Top 5 productos más caros
            </h3>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[var(--color-background)]">
                {['Nombre', 'Categoría', 'Precio'].map((h) => (
                  <th
                    key={h}
                    className="px-5 py-3 text-left font-sans font-semibold text-xs uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)]"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {topProductos.slice(0, 5).map((prod, idx) => (
                <tr
                  key={prod._id}
                  className={idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]'}
                >
                  <td className="px-5 py-3 font-display font-semibold text-[var(--color-text-primary)]">
                    {prod.nombre}
                  </td>
                  <td className="px-5 py-3 font-sans text-[var(--color-text-secondary)]">
                    {prod.categoria}
                  </td>
                  <td className="px-5 py-3 font-mono font-bold text-[var(--color-text-primary)]">
                    {formatQ(prod.precio)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {porCategoria.length > 0 && (
        <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
          <div className="px-5 py-4 border-b border-[var(--color-border)]">
            <h3 className="font-display font-semibold text-base text-[var(--color-text-primary)]">
              Estadísticas por categoría
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-[var(--color-background)]">
                  {['Categoría', 'Total', 'Disponibles', 'Precio mín', 'Precio máx', 'Promedio'].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left font-sans font-semibold text-xs uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)] whitespace-nowrap"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {porCategoria.map((cat, idx) => (
                  <tr
                    key={cat._id}
                    className={idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]'}
                  >
                    <td className="px-4 py-3 font-display font-semibold text-[var(--color-text-primary)]">
                      {cat.categoria_nombre}
                    </td>
                    <td className="px-4 py-3 font-mono text-[var(--color-text-primary)]">
                      {cat.total_productos}
                    </td>
                    <td className="px-4 py-3 font-mono text-[var(--color-text-primary)]">
                      {cat.disponibles}
                    </td>
                    <td className="px-4 py-3 font-mono text-[var(--color-text-primary)]">
                      {formatQ(cat.precio_minimo)}
                    </td>
                    <td className="px-4 py-3 font-mono text-[var(--color-text-primary)]">
                      {formatQ(cat.precio_maximo)}
                    </td>
                    <td className="px-4 py-3 font-mono font-semibold text-[var(--color-text-primary)]">
                      {formatQ(cat.precio_promedio)}
                    </td>
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

function ProductFormModal({ open, onOpenChange, product, onSuccess }) {
  const isEdit = !!product
  const queryClient = useQueryClient()

  const EMPTY = { sku: '', nombre: '', descripcion: '', precio: '', categoria_slug: '', disponible: true, estado: 'activo', atributos: {}, stock: '' }
  const [form, setForm] = useState(EMPTY)

  useEffect(() => {
    if (open) {
      setForm(isEdit ? {
        sku: product.sku || '',
        nombre: product.nombre || '',
        descripcion: product.descripcion || '',
        precio: String(product.precio || ''),
        categoria_slug: product.categoria?.slug || '',
        disponible: product.disponible ?? true,
        estado: product.estado || 'activo',
        atributos: { ...(product.atributos || {}) },
        stock: isEdit ? (product.stock ?? '') : '',
      } : EMPTY)
    }
  }, [open, product])

  const { data: categoriesData } = useQuery({
    queryKey: ['categories'],
    queryFn: () => getCategories().then((r) => r.data),
  })
  const categories = categoriesData || []

  const mutation = useMutation({
    mutationFn: (payload) =>
      isEdit
        ? updateProduct(product._id, payload)
        : createProduct(payload),
    onSuccess: () => {
      toast.success(isEdit ? 'Producto actualizado.' : 'Producto creado.')
      queryClient.invalidateQueries({ queryKey: ['admin-products'] })
      queryClient.invalidateQueries({ queryKey: ['products'] })
      onOpenChange(false)
      onSuccess?.()
    },
    onError: (err) => {
      const detail = err?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Error al guardar el producto.')
    },
  })

  function set(key, value) { setForm((p) => ({ ...p, [key]: value })) }
  function setAttr(key, value) { setForm((p) => ({ ...p, atributos: { ...p.atributos, [key]: value } })) }

  // Carga el esquema de campos desde MongoDB cuando cambia la categoría
  const { data: schemaData } = useQuery({
    queryKey: ['category-schema', form.categoria_slug],
    queryFn: () => getCategorySchema(form.categoria_slug).then((r) => r.data),
    enabled: !!form.categoria_slug,
    staleTime: 5 * 60 * 1000,
  })
  const attrFields = schemaData?.atributos || []

  function handleSubmit(e) {
    e.preventDefault()
    if (!form.nombre || !form.precio) return toast.error('Nombre y precio son obligatorios.')
    if (!isEdit && !form.sku) return toast.error('El SKU es obligatorio.')
    if (!isEdit && !form.categoria_slug) return toast.error('Selecciona una categoría.')

    const atributos = {}
    attrFields.forEach(({ nombre, tipo }) => {
      const v = form.atributos[nombre]
      if (v === '' || v === undefined || v === null) return
      atributos[nombre] = tipo === 'number' ? Number(v) : v
    })

    const payload = isEdit
      ? { nombre: form.nombre, descripcion: form.descripcion, precio: Number(form.precio), disponible: form.disponible, estado: form.estado, atributos, ...(form.stock !== '' && { stock: Number(form.stock) }) }
      : { sku: form.sku, nombre: form.nombre, descripcion: form.descripcion, precio: Number(form.precio), categoria_slug: form.categoria_slug, atributos, stock: Number(form.stock) || 0 }

    mutation.mutate(payload)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogTitle>{isEdit ? 'Editar producto' : 'Nuevo producto'}</DialogTitle>
        <DialogDescription>
          {isEdit ? `SKU: ${product?.sku}` : 'Los campos con * son obligatorios.'}
        </DialogDescription>

        <form onSubmit={handleSubmit} className="space-y-4 mt-2">
          <div className="grid grid-cols-2 gap-3">
            {!isEdit && (
              <div>
                <Label>SKU *</Label>
                <Input value={form.sku} onChange={(e) => set('sku', e.target.value)} placeholder="LAP-001" />
              </div>
            )}
            <div className={isEdit ? 'col-span-2' : ''}>
              <Label>Nombre *</Label>
              <Input value={form.nombre} onChange={(e) => set('nombre', e.target.value)} placeholder="Laptop ASUS..." />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Precio (GTQ) *</Label>
              <Input type="number" step="0.01" min="0" value={form.precio} onChange={(e) => set('precio', e.target.value)} placeholder="999.99" />
            </div>
            {!isEdit ? (
              <div>
                <Label>Categoría *</Label>
                <Select value={form.categoria_slug} onValueChange={(v) => { set('categoria_slug', v); set('atributos', {}) }}>
                  <SelectTrigger><SelectValue placeholder="Seleccionar..." /></SelectTrigger>
                  <SelectContent>
                    {categories.map((c) => (
                      <SelectItem key={c.slug} value={c.slug}>{c.nombre}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : (
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
              <input type="checkbox" checked={form.disponible} onChange={(e) => set('disponible', e.target.checked)}
                className="h-4 w-4 accent-[var(--color-action)]" />
              <span className="font-sans text-sm text-[var(--color-text-primary)]">Disponible (en stock)</span>
            </label>
          )}

          {attrFields.length > 0 && (
            <>
              <Separator />
              <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                Atributos de {categories.find(c => c.slug === form.categoria_slug)?.nombre || 'categoría'}
              </p>
              <div className="grid grid-cols-2 gap-3">
                {attrFields.map((field) => (
                  <div key={field.nombre} className={field.tipo === 'boolean' ? 'flex items-center gap-2 col-span-1' : ''}>
                    {field.tipo === 'boolean' ? (
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={!!form.atributos[field.nombre]}
                          onChange={(e) => setAttr(field.nombre, e.target.checked)}
                          className="h-4 w-4 accent-[var(--color-action)]"
                        />
                        <span className="font-sans text-sm text-[var(--color-text-primary)]">{field.etiqueta}</span>
                      </label>
                    ) : (
                      <>
                        <Label>{field.etiqueta}</Label>
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
            </>
          )}

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

function ProductsSection() {
  const [page, setPage] = useState(1)
  const [modalOpen, setModalOpen] = useState(false)
  const [editProduct, setEditProduct] = useState(null)
  const PAGE_SIZE = 15
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['admin-products', page],
    queryFn: () => getProducts({ page, page_size: PAGE_SIZE }).then((r) => r.data),
    placeholderData: keepPreviousData,
  })

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

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={openCreate}>
          <Plus size={14} /> Nuevo producto
        </Button>
      </div>

      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[var(--color-background)]">
                {['Nombre', 'Categoría', 'Precio', 'Stock', 'Disponible', 'Acciones'].map((h) => (
                  <th key={h} className="px-4 py-3 text-left font-sans font-semibold text-xs uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)]">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {products.map((prod, idx) => (
                <tr
                  key={prod._id}
                  className={cn(
                    'border-b border-[var(--color-border)] last:border-0',
                    idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]'
                  )}
                >
                  <td className="px-4 py-3 font-display font-semibold text-[var(--color-text-primary)] max-w-[200px]">
                    <span className="line-clamp-1">{prod.nombre}</span>
                    <span className="font-mono font-normal text-[10px] text-[var(--color-text-muted)] block">{prod.sku}</span>
                  </td>
                  <td className="px-4 py-3 font-sans text-[var(--color-text-secondary)]">
                    {prod.categoria?.nombre || '—'}
                  </td>
                  <td className="px-4 py-3 font-mono font-semibold text-[var(--color-text-primary)]">
                    {formatQ(prod.precio)}
                  </td>
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
                    <Badge variant={prod.disponible ? 'success' : 'error'}>
                      {prod.disponible ? 'Sí' : 'No'}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <Button variant="ghost" size="sm" onClick={() => openEdit(prod)}>
                        <Edit size={13} /> Editar
                      </Button>
                      <Button variant="ghost" size="sm" asChild>
                        <Link to={`/admin/products/${prod._id}/history`}>
                          <History size={13} /> Historial
                        </Link>
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-[var(--color-error)] hover:text-[var(--color-error)] hover:bg-[var(--color-error)]/10"
                        onClick={() => handleDelete(prod)}
                        disabled={deleteMutation.isPending}
                      >
                        <Trash2 size={13} />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-5">
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Anterior
          </Button>
          <span className="font-sans text-sm text-[var(--color-text-secondary)]">{page} / {totalPages}</span>
          <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
            Siguiente
          </Button>
        </div>
      )}

      <ProductFormModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        product={editProduct}
      />
    </div>
  )
}

function CategoriesSection() {
  const queryClient = useQueryClient()

  // ── state ──────────────────────────────────────────────────────────────────
  const [createOpen, setCreateOpen] = useState(false)
  const [editTarget, setEditTarget] = useState(null) // category being edited
  const [editOpen, setEditOpen] = useState(false)

  // create form
  const [newNombre, setNewNombre] = useState('')
  const [newSlug, setNewSlug] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newPadreId, setNewPadreId] = useState('')
  const [newAttrs, setNewAttrs] = useState([])

  // edit form (schema only)
  const [editAttrs, setEditAttrs] = useState([])

  // ── data ───────────────────────────────────────────────────────────────────
  const { data: cats = [], isLoading } = useQuery({
    queryKey: ['admin-categories'],
    queryFn: () => getAdminCategories().then((r) => r.data),
  })

  // ── mutations ──────────────────────────────────────────────────────────────
  const createMut = useMutation({
    mutationFn: (data) => createCategory(data),
    onSuccess: () => {
      toast.success('Categoría creada.')
      queryClient.invalidateQueries({ queryKey: ['admin-categories'] })
      queryClient.invalidateQueries({ queryKey: ['categories'] })
      setCreateOpen(false)
      setNewNombre(''); setNewSlug(''); setNewDesc(''); setNewPadreId(''); setNewAttrs([])
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

  // ── helpers ────────────────────────────────────────────────────────────────
  function slugify(str) {
    return str.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  }

  function emptyAttr() {
    return { nombre: '', etiqueta: '', tipo: 'string', requerido: false, placeholder: '' }
  }

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

  function openEdit(cat) {
    setEditTarget(cat)
    setEditAttrs(cat.atributos.length ? cat.atributos.map((a) => ({ ...a })) : [])
    setEditOpen(true)
  }

  function handleDelete(cat) {
    if (!window.confirm(`¿Eliminar categoría "${cat.nombre}"? Esto también eliminará su esquema de campos.`)) return
    deleteMut.mutate(cat.slug)
  }

  // ── render ─────────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus size={14} /> Nueva categoría
        </Button>
      </div>

      {/* Category list */}
      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-[var(--color-background)]">
              {['Nombre', 'Slug', 'Padre', 'Campos (MongoDB)', 'Acciones'].map((h) => (
                <th key={h} className="px-4 py-3 text-left font-sans font-semibold text-xs uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)]">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {cats.map((cat, idx) => (
              <tr
                key={cat.id}
                className={cn(
                  'border-b border-[var(--color-border)] last:border-0',
                  idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]'
                )}
              >
                <td className="px-4 py-3 font-display font-semibold text-[var(--color-text-primary)]">
                  {cat.nombre}
                  {!cat.activa && <Badge variant="error" className="ml-2 text-[10px]">inactiva</Badge>}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-[var(--color-text-secondary)]">{cat.slug}</td>
                <td className="px-4 py-3 font-sans text-xs text-[var(--color-text-secondary)]">
                  {cat.padre_id
                    ? cats.find((c) => c.id === cat.padre_id)?.nombre || `#${cat.padre_id}`
                    : <span className="text-[var(--color-text-muted)]">—</span>}
                </td>
                <td className="px-4 py-3 font-sans text-[var(--color-text-secondary)]">
                  {cat.atributos.length > 0
                    ? cat.atributos.map((a) => a.etiqueta).join(', ')
                    : <span className="text-[var(--color-text-muted)] italic">sin campos</span>}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1">
                    <Button variant="ghost" size="sm" onClick={() => openEdit(cat)}>
                      <Edit size={13} /> Editar campos
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-[var(--color-error)] hover:text-[var(--color-error)] hover:bg-[var(--color-error)]/10"
                      onClick={() => handleDelete(cat)}
                      disabled={deleteMut.isPending}
                    >
                      <Trash2 size={13} />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
            {cats.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center font-sans text-sm text-[var(--color-text-muted)]">
                  No hay categorías todavía.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ── Create dialog ───────────────────────────────────────────────────── */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogTitle>Nueva categoría</DialogTitle>
          <DialogDescription>
            Los datos básicos se guardan en MySQL. Los campos personalizados se guardan en MongoDB.
          </DialogDescription>
          <form
            className="space-y-4 mt-2"
            onSubmit={(e) => {
              e.preventDefault()
              createMut.mutate({
                nombre: newNombre,
                slug: newSlug || slugify(newNombre),
                descripcion: newDesc || undefined,
                padre_id: newPadreId ? Number(newPadreId) : undefined,
                atributos: newAttrs.filter((a) => a.nombre && a.etiqueta),
              })
            }}
          >
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Nombre</Label>
                <Input
                  required
                  value={newNombre}
                  onChange={(e) => {
                    setNewNombre(e.target.value)
                    if (!newSlug) setNewSlug(slugify(e.target.value))
                  }}
                  placeholder="ej. Laptops"
                />
              </div>
              <div className="space-y-1">
                <Label>Slug (URL)</Label>
                <Input
                  required
                  value={newSlug}
                  onChange={(e) => setNewSlug(e.target.value)}
                  placeholder="ej. laptops"
                  className="font-mono text-sm"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Descripción (opcional)</Label>
                <Input value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="Breve descripción..." />
              </div>
              <div className="space-y-1">
                <Label>Categoría padre (opcional)</Label>
                <Select value={newPadreId} onValueChange={setNewPadreId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Ninguna (categoría raíz)" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">Ninguna (categoría raíz)</SelectItem>
                    {cats.map((c) => (
                      <SelectItem key={c.id} value={String(c.id)}>{c.nombre}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <Separator />
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                  Campos personalizados (MongoDB)
                </p>
                <Button type="button" variant="secondary" size="sm" onClick={() => setNewAttrs((a) => [...a, emptyAttr()])}>
                  <Plus size={13} /> Agregar campo
                </Button>
              </div>
              <p className="font-sans text-xs text-[var(--color-text-muted)]">
                Estos campos aparecerán al crear/editar productos de esta categoría.
              </p>
              {newAttrs.length === 0 && (
                <p className="font-sans text-xs text-[var(--color-text-muted)] italic py-2">
                  Sin campos aún. Agrega los atributos que diferencian esta categoría.
                </p>
              )}
              <div className="space-y-2">
                {newAttrs.map((attr, i) => (
                  <AttrRow
                    key={i}
                    attr={attr}
                    onChange={(updated) => setNewAttrs((a) => a.map((x, j) => j === i ? updated : x))}
                    onRemove={() => setNewAttrs((a) => a.filter((_, j) => j !== i))}
                  />
                ))}
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <DialogClose asChild>
                <Button type="button" variant="secondary">Cancelar</Button>
              </DialogClose>
              <Button type="submit" loading={createMut.isPending}>Crear categoría</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* ── Edit schema dialog ──────────────────────────────────────────────── */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogTitle>Editar campos — {editTarget?.nombre}</DialogTitle>
          <DialogDescription>
            Modifica los campos personalizados de esta categoría (solo MongoDB).
          </DialogDescription>
          <form
            className="space-y-4 mt-2"
            onSubmit={(e) => {
              e.preventDefault()
              schemaMut.mutate({
                slug: editTarget.slug,
                data: { atributos: editAttrs.filter((a) => a.nombre && a.etiqueta) },
              })
            }}
          >
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="font-sans text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                  Campos personalizados
                </p>
                <Button type="button" variant="secondary" size="sm" onClick={() => setEditAttrs((a) => [...a, emptyAttr()])}>
                  <Plus size={13} /> Agregar campo
                </Button>
              </div>
              {editAttrs.length === 0 && (
                <p className="font-sans text-xs text-[var(--color-text-muted)] italic py-2">Sin campos. Agrega los atributos de esta categoría.</p>
              )}
              <div className="space-y-2">
                {editAttrs.map((attr, i) => (
                  <AttrRow
                    key={i}
                    attr={attr}
                    onChange={(updated) => setEditAttrs((a) => a.map((x, j) => j === i ? updated : x))}
                    onRemove={() => setEditAttrs((a) => a.filter((_, j) => j !== i))}
                  />
                ))}
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <DialogClose asChild>
                <Button type="button" variant="secondary">Cancelar</Button>
              </DialogClose>
              <Button type="submit" loading={schemaMut.isPending}>Guardar esquema</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function UsersSection() {
  const [page, setPage] = useState(1)
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['admin-users', page],
    queryFn: () => getAdminUsers(page).then((r) => r.data),
    placeholderData: keepPreviousData,
  })

  const mutation = useMutation({
    mutationFn: ({ userId, roles }) => updateUserRoles(userId, roles),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-users'] }),
    onError: (err) => toast.error(err?.response?.data?.detail || 'No se pudo actualizar los roles.'),
  })

  function toggleRole(user, role) {
    const current = new Set(user.roles)
    if (current.has(role)) current.delete(role)
    else current.add(role)
    mutation.mutate({ userId: user.id, roles: [...current] })
  }

  const users = data?.items || []
  const totalPages = data?.total_pages || 1

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    )
  }

  return (
    <div>
      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[var(--color-background)]">
                {['Usuario', 'Email', 'Estado', 'Roles (clic para cambiar)'].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-3 text-left font-sans font-semibold text-xs uppercase tracking-wider text-[var(--color-text-muted)] border-b border-[var(--color-border)] whitespace-nowrap"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.map((user, idx) => (
                <tr
                  key={user.id}
                  className={cn(
                    'border-b border-[var(--color-border)] last:border-0',
                    idx % 2 === 0 ? 'bg-[var(--color-surface)]' : 'bg-[var(--color-background)]'
                  )}
                >
                  <td className="px-4 py-3">
                    <p className="font-display font-semibold text-[var(--color-text-primary)]">
                      {user.nombre} {user.apellido}
                    </p>
                    <p className="font-mono text-[10px] text-[var(--color-text-muted)]">#{user.id}</p>
                  </td>
                  <td className="px-4 py-3 font-sans text-[var(--color-text-secondary)] text-xs">
                    {user.email}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={user.estado === 'activo' ? 'success' : 'error'}>
                      {user.estado}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1.5">
                      {ALL_ROLES.map((role) => {
                        const meta = ROLE_META[role]
                        const { Icon } = meta
                        const hasRole = user.roles.includes(role)
                        return (
                          <button
                            key={role}
                            onClick={() => toggleRole(user, role)}
                            disabled={mutation.isPending}
                            className={cn(
                              'inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-sans font-semibold border transition-all duration-150 disabled:opacity-50',
                              hasRole ? meta.active : meta.inactive
                            )}
                          >
                            <Icon size={11} strokeWidth={2} />
                            {meta.label}
                          </button>
                        )
                      })}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 mt-5">
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Anterior
          </Button>
          <span className="font-sans text-sm text-[var(--color-text-secondary)]">{page} / {totalPages}</span>
          <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
            Siguiente
          </Button>
        </div>
      )}
    </div>
  )
}

export default function AdminPage() {
  const [activeSection, setActiveSection] = useState('stats')

  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <div className="flex">
        <aside className="w-56 shrink-0 min-h-screen border-r border-[var(--color-border)] bg-[var(--color-surface)] pt-8">
          <div className="px-5 mb-6">
            <h1 className="font-display font-bold text-base text-[var(--color-text-primary)]">
              Panel Admin
            </h1>
            <p className="font-sans text-xs text-[var(--color-text-muted)] mt-0.5">TiendaYa</p>
          </div>
          <Separator />
          <nav className="p-3 mt-2 space-y-1">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveSection(item.id)}
                  className={cn(
                    'w-full flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-md)] text-sm font-sans font-medium transition-colors text-left',
                    activeSection === item.id
                      ? 'bg-[var(--color-action)] text-white'
                      : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] hover:text-[var(--color-text-primary)]'
                  )}
                >
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
          {activeSection === 'stats' && <StatsSection />}
          {activeSection === 'products' && <ProductsSection />}
          {activeSection === 'categories' && <CategoriesSection />}
          {activeSection === 'users' && <UsersSection />}
        </main>
      </div>
    </div>
  )
}
