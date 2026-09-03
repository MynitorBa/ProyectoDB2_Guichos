import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { History } from 'lucide-react'
import { getProduct } from '../api/products'
import { ProductFormModal, VariantsModal, OffersModal } from './AdminPage'
import { RecordMode } from '../components/ui/record-dialog'
import { Badge } from '../components/ui/badge'

const PRODUCT_STATE_BADGE = {
  activo: 'success',
  borrador: 'default',
  descontinuado: 'default',
}

const TABS = [
  ['general', 'Datos e imágenes'],
  ['variants', 'Variantes'],
  ['offers', 'Ofertas por vendedor'],
]

export default function AdminProductPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [tab, setTab] = useState(params.get('tab') || 'general')
  const fresh = id === 'new'
  const { data: product, isLoading, isError } = useQuery({
    queryKey: ['admin-product-record', id],
    queryFn: () => getProduct(id).then(r => r.data),
    enabled: !fresh,
  })
  const back = () => navigate('/admin?section=products')

  return (
    <main className="max-w-6xl mx-auto p-6 space-y-6">
      <Link to="/admin?section=products" className="text-sm text-[var(--color-action)] hover:underline">← Productos</Link>

      {!fresh && isLoading ? (
        <p className="text-[var(--color-text-secondary)]">Cargando ficha…</p>
      ) : !fresh && (isError || !product) ? (
        <p role="alert" className="text-[var(--color-error)]">No se pudo cargar el producto.</p>
      ) : (
        <>
          <header className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold font-display">
                {fresh ? 'Nuevo producto' : product.nombre}
              </h1>
              {!fresh && (
                <div className="flex items-center gap-2 mt-1.5">
                  <span className="text-sm font-mono text-[var(--color-text-muted)]">{product.sku}</span>
                  <Badge variant={PRODUCT_STATE_BADGE[product.estado] || 'default'}>{product.estado}</Badge>
                </div>
              )}
            </div>
            {!fresh && (
              <Link
                to={`/admin/products/${id}/history`}
                className="flex items-center gap-1.5 text-sm text-[var(--color-action)] hover:underline flex-shrink-0"
              >
                <History size={14} />
                Historial
              </Link>
            )}
          </header>

          {!fresh && (
            <nav className="flex flex-wrap gap-2 border-b border-[var(--color-border)] pb-4">
              {TABS.map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setTab(key)}
                  className={[
                    'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
                    tab === key
                      ? 'bg-[var(--color-action)] text-white shadow-[var(--shadow-sm)]'
                      : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-border)]',
                  ].join(' ')}
                >
                  {label}
                </button>
              ))}
            </nav>
          )}

          <RecordMode.Provider value={true}>
            {(fresh || tab === 'general') && (
              <ProductFormModal open onOpenChange={back} product={product} onDuplicateFound={p => navigate(`/admin/products/${p._id}`)} />
            )}
            {!fresh && tab === 'variants' && (
              <VariantsModal open onOpenChange={() => setTab('general')} product={product} />
            )}
            {!fresh && tab === 'offers' && (
              <OffersModal open onOpenChange={() => setTab('general')} product={product} />
            )}
          </RecordMode.Provider>
        </>
      )}
    </main>
  )
}
