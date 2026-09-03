import { useState } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { getAdminCategories, updateCategorySchema, createCategory } from '../api/admin'
import { getAdminProducts } from '../api/products'
import { AttrRow } from './AdminPage'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Badge } from '../components/ui/badge'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../components/ui/select'

function NewCategory() {
  const navigate = useNavigate()
  const cache = useQueryClient()
  const [form, setForm] = useState({ nombre: '', slug: '', descripcion: '', padre_id: '', sku_prefix: '' })
  const [attrs, setAttrs] = useState([])
  const { data: categories = [] } = useQuery({
    queryKey: ['admin-categories'],
    queryFn: () => getAdminCategories().then(r => r.data),
  })
  const mutation = useMutation({
    mutationFn: () => createCategory({
      ...form,
      padre_id: form.padre_id ? Number(form.padre_id) : null,
      sku_prefix: form.sku_prefix || undefined,
      atributos: attrs,
    }),
    onSuccess: () => {
      cache.invalidateQueries({ queryKey: ['admin-categories'] })
      cache.invalidateQueries({ queryKey: ['categories'] })
      toast.success('Categoría creada.')
      navigate('/admin/categories/' + form.slug)
    },
    onError: e => {
      const d = e.response?.data?.detail
      toast.error(typeof d === 'string' ? d : d?.message || 'No se pudo crear la categoría.')
    },
  })

  return (
    <main className="max-w-5xl mx-auto p-6 space-y-6">
      <Link to="/admin?section=categories" className="text-sm text-[var(--color-action)] hover:underline">← Categorías</Link>
      <h1 className="text-2xl font-bold font-display">Nueva categoría</h1>
      <form
        className="border border-[var(--color-border)] rounded-xl p-6 space-y-5 bg-[var(--color-surface)]"
        onSubmit={e => { e.preventDefault(); mutation.mutate() }}
      >
        <div className="grid sm:grid-cols-2 gap-5">
          {[['nombre', 'Nombre'], ['slug', 'Slug (identificador de URL)'], ['descripcion', 'Descripción'], ['sku_prefix', 'Prefijo SKU']].map(([key, label]) => (
            <div key={key} className="space-y-1.5">
              <Label htmlFor={key}>{label}</Label>
              <Input
                id={key}
                required={['nombre', 'slug'].includes(key)}
                value={form[key]}
                onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
              />
            </div>
          ))}
        </div>
        <div className="space-y-1.5">
          <Label>Categoría padre</Label>
          <Select value={form.padre_id || 'none'} onValueChange={v => setForm(f => ({ ...f, padre_id: v === 'none' ? '' : v }))}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="none">Sin categoría padre</SelectItem>
              {categories.map(c => <SelectItem key={c.id} value={String(c.id)}>{c.nombre}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        {attrs.length > 0 && (
          <div className="space-y-3">
            <h2 className="font-semibold">Atributos de los productos</h2>
            {attrs.map((a, i) => (
              <AttrRow
                key={i}
                attr={a}
                onChange={v => setAttrs(rows => rows.map((r, j) => j === i ? v : r))}
                onRemove={() => setAttrs(rows => rows.filter((_, j) => j !== i))}
              />
            ))}
          </div>
        )}
        <div className="flex gap-3 pt-1">
          <Button
            type="button"
            variant="secondary"
            onClick={() => setAttrs(rows => [...rows, { nombre: '', etiqueta: '', tipo: 'string', requerido: false, placeholder: '' }])}
          >
            Agregar campo
          </Button>
          <Button type="submit" loading={mutation.isPending}>Crear categoría</Button>
        </div>
      </form>
    </main>
  )
}

function CategoryForm({ category }) {
  const [attrs, setAttrs] = useState(category.atributos || [])
  const [prefix, setPrefix] = useState(category.sku_prefix || '')
  const cache = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => updateCategorySchema(category.slug, { atributos: attrs, sku_prefix: prefix, categoria_nombre: category.nombre }),
    onSuccess: () => {
      toast.success('Campos actualizados.')
      cache.invalidateQueries({ queryKey: ['admin-categories'] })
      cache.invalidateQueries({ queryKey: ['category-schema'] })
    },
    onError: e => toast.error(e.response?.data?.detail || 'No se pudieron guardar los campos.'),
  })

  return (
    <form
      className="border border-[var(--color-border)] rounded-xl p-6 space-y-5 bg-[var(--color-surface)]"
      onSubmit={e => { e.preventDefault(); mutation.mutate() }}
    >
      <h2 className="text-xl font-semibold font-display">Campos de la categoría</h2>
      <div className="space-y-1.5">
        <Label>Prefijo SKU</Label>
        <Input className="max-w-xs" value={prefix} maxLength={3} onChange={e => setPrefix(e.target.value.toUpperCase())} />
      </div>
      <div className="space-y-3">
        {attrs.map((attr, i) => (
          <AttrRow
            key={i}
            attr={attr}
            onChange={value => setAttrs(rows => rows.map((r, j) => j === i ? value : r))}
            onRemove={() => setAttrs(rows => rows.filter((_, j) => j !== i))}
          />
        ))}
      </div>
      <div className="flex gap-3">
        <Button
          type="button"
          variant="secondary"
          onClick={() => setAttrs(rows => [...rows, { nombre: '', etiqueta: '', tipo: 'string', requerido: false, placeholder: '' }])}
        >
          Agregar campo
        </Button>
        <Button loading={mutation.isPending} type="submit">Guardar campos</Button>
      </div>
      <p className="text-xs text-[var(--color-text-muted)]">
        Cambiar el esquema no rellena ni modifica automáticamente atributos históricos de productos existentes.
      </p>
    </form>
  )
}

function ExistingCategory() {
  const { slug } = useParams()
  const [page, setPage] = useState(1)
  const { data: categories = [], isLoading } = useQuery({
    queryKey: ['admin-categories'],
    queryFn: () => getAdminCategories().then(r => r.data),
  })
  const { data: products, isError } = useQuery({
    queryKey: ['category-products', slug, page],
    queryFn: () => getAdminProducts({ categoria: slug, estado: 'todos', page, page_size: 20 }).then(r => r.data),
  })
  const category = categories.find(c => c.slug === slug)

  return (
    <main className="max-w-6xl mx-auto p-6 space-y-6">
      <Link to="/admin?section=categories" className="text-sm text-[var(--color-action)] hover:underline">← Categorías</Link>
      {isLoading ? (
        <p className="text-[var(--color-text-secondary)]">Cargando…</p>
      ) : !category ? (
        <p>Categoría no encontrada.</p>
      ) : (
        <>
          <header className="flex items-start gap-4">
            <div>
              <h1 className="text-2xl font-bold font-display">{category.nombre}</h1>
              {category.descripcion && (
                <p className="text-[var(--color-text-secondary)] mt-1">{category.descripcion}</p>
              )}
              <div className="flex items-center gap-2 mt-2 flex-wrap">
                <Badge variant={category.activa ? 'success' : 'default'}>{category.activa ? 'Activa' : 'Inactiva'}</Badge>
                <span className="text-xs font-mono text-[var(--color-text-muted)]">{category.slug}</span>
                {categories.find(c => c.id === category.padre_id) && (
                  <span className="text-xs text-[var(--color-text-muted)]">
                    ↳ {categories.find(c => c.id === category.padre_id)?.nombre}
                  </span>
                )}
              </div>
            </div>
          </header>

          <CategoryForm key={category.id} category={category} />

          <section className="space-y-4">
            <h2 className="text-xl font-semibold font-display">
              Productos asociados{' '}
              <span className="text-[var(--color-text-muted)] font-normal text-base">({products?.total || 0})</span>
            </h2>
            {isError ? (
              <p role="alert" className="text-[var(--color-error)]">No se pudieron consultar los productos.</p>
            ) : (
              <div className="space-y-2">
                {products?.items.map(p => (
                  <Link
                    key={p._id}
                    to={`/admin/products/${p._id}`}
                    className="flex items-center justify-between border border-[var(--color-border)] rounded-xl px-4 py-3 bg-[var(--color-surface)] hover:border-[var(--color-action)] transition-colors group"
                  >
                    <div>
                      <span className="font-medium group-hover:text-[var(--color-action)] transition-colors">{p.nombre}</span>
                      <span className="text-xs font-mono text-[var(--color-text-muted)] ml-2">{p.sku}</span>
                    </div>
                    <Badge variant={p.estado === 'activo' ? 'success' : 'default'}>{p.estado}</Badge>
                  </Link>
                ))}
              </div>
            )}
            <div className="flex justify-center items-center gap-3 pt-1">
              <Button variant="secondary" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Anterior</Button>
              <span className="text-sm text-[var(--color-text-secondary)]">{page} / {products?.total_pages || 1}</span>
              <Button variant="secondary" disabled={page >= (products?.total_pages || 1)} onClick={() => setPage(p => p + 1)}>Siguiente</Button>
            </div>
          </section>
        </>
      )}
    </main>
  )
}

export default function AdminCategoryPage() {
  const { slug } = useParams()
  return slug === 'new' ? <NewCategory /> : <ExistingCategory />
}
