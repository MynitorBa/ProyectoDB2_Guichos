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
import { formatearPrefijoSku, formatearSlug, limpiarSlug, PREFIJO_SKU_PATRON, SLUG_PATRON } from '../lib/utils'

function Ayuda({ children, error }) {
  return (
    <p className={`text-xs ${error ? 'text-[var(--color-error)]' : 'text-[var(--color-text-muted)]'}`}>{children}</p>
  )
}

function NewCategory() {
  const navigate = useNavigate()
  const cache = useQueryClient()
  const [form, setForm] = useState({ nombre: '', slug: '', descripcion: '', padre_id: '', sku_prefix: '' })
  // Mientras el admin no toque el slug, se genera solo a partir del nombre.
  const [slugEditado, setSlugEditado] = useState(false)
  const [attrs, setAttrs] = useState([])
  const { data: categories = [] } = useQuery({
    queryKey: ['admin-categories'],
    queryFn: () => getAdminCategories().then(r => r.data),
  })
  const slug = limpiarSlug(form.slug)
  const prefijoIncompleto = form.sku_prefix.length > 0 && form.sku_prefix.length < 3
  const mutation = useMutation({
    mutationFn: () => createCategory({
      ...form,
      slug,
      padre_id: form.padre_id ? Number(form.padre_id) : null,
      sku_prefix: form.sku_prefix || undefined,
      atributos: attrs,
    }),
    onSuccess: () => {
      cache.invalidateQueries({ queryKey: ['admin-categories'] })
      cache.invalidateQueries({ queryKey: ['categories'] })
      toast.success('Categoría creada.')
      navigate('/admin/categories/' + slug)
    },
    onError: e => {
      const d = e.response?.data?.detail
      // 422 de Pydantic: lista de errores con el mensaje del validador.
      const validacion = Array.isArray(d) ? d[0]?.msg?.replace(/^Value error, /, '') : null
      toast.error(typeof d === 'string' ? d : validacion || d?.message || 'No se pudo crear la categoría.')
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
          <div className="space-y-1.5">
            <Label htmlFor="nombre">Nombre</Label>
            <Input
              id="nombre"
              required
              placeholder="ej. Ropa deportiva"
              value={form.nombre}
              onChange={e => {
                const nombre = e.target.value
                setForm(f => ({ ...f, nombre, ...(slugEditado ? {} : { slug: limpiarSlug(nombre) }) }))
              }}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="slug">Slug (identificador de URL)</Label>
            <Input
              id="slug"
              required
              placeholder="ej. ropa-deportiva"
              pattern={SLUG_PATRON}
              title="Solo minúsculas sin tildes, números y guiones (ej. ropa-deportiva)."
              maxLength={120}
              className="font-mono text-sm"
              value={form.slug}
              onChange={e => { setSlugEditado(true); setForm(f => ({ ...f, slug: formatearSlug(e.target.value) })) }}
              onBlur={() => setForm(f => ({ ...f, slug: limpiarSlug(f.slug) }))}
            />
            <Ayuda>
              Minúsculas, números y guiones. URL: <span className="font-mono">/catalog?categoria={slug || '…'}</span>
            </Ayuda>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="descripcion">Descripción</Label>
            <Input
              id="descripcion"
              placeholder="Breve descripción…"
              value={form.descripcion}
              onChange={e => setForm(f => ({ ...f, descripcion: e.target.value }))}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="sku_prefix">Prefijo SKU <span className="text-[var(--color-text-muted)] font-normal">(3 letras, opcional)</span></Label>
            <Input
              id="sku_prefix"
              placeholder="ej. DEP"
              pattern={PREFIJO_SKU_PATRON}
              title="Exactamente 3 letras (ej. DEP)."
              maxLength={3}
              className="font-mono text-sm tracking-widest uppercase w-28"
              value={form.sku_prefix}
              onChange={e => setForm(f => ({ ...f, sku_prefix: formatearPrefijoSku(e.target.value) }))}
            />
            <Ayuda error={prefijoIncompleto}>
              {prefijoIncompleto
                ? 'Faltan letras: el prefijo debe tener exactamente 3.'
                : <>Los productos tendrán SKU como <span className="font-mono">{form.sku_prefix || 'XXX'}-1A2B3C4D</span>. Si lo dejas vacío se usan las 3 primeras letras del slug.</>}
            </Ayuda>
          </div>
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
        <Input
          className="max-w-xs font-mono tracking-widest uppercase"
          value={prefix}
          maxLength={3}
          pattern={PREFIJO_SKU_PATRON}
          title="Exactamente 3 letras (ej. DEP)."
          placeholder="ej. DEP"
          onChange={e => setPrefix(formatearPrefijoSku(e.target.value))}
        />
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
