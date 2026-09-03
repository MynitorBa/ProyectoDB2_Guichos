import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, Image as ImageIcon } from 'lucide-react'
import { getProducts } from '../api/products'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from './ui/dialog'
import { Button } from './ui/button'
import { Input } from './ui/input'

export default function ProductPicker({ value, onSelect }) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)

  useEffect(() => {
    const timer = setTimeout(() => { setQ(search); setPage(1) }, 250)
    return () => clearTimeout(timer)
  }, [search])

  const { data, isLoading, isError } = useQuery({
    queryKey: ['product-picker', q, page],
    enabled: open,
    queryFn: () => getProducts({ q, page, page_size: 12, orden: 'nombre_asc' }).then(r => r.data),
  })

  return (
    <div className="space-y-2">
      <Button type="button" variant="secondary" onClick={() => setOpen(true)} className="gap-2">
        <Search size={16} />
        {value ? 'Cambiar producto' : 'Buscar y seleccionar producto'}
      </Button>

      {value && (
        <div className="flex items-center gap-3 px-3 py-2.5 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl">
          <p className="font-semibold text-sm flex-1">{value.nombre}</p>
          <span className="text-xs font-mono text-[var(--color-text-muted)]">{value.sku}</span>
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-4xl">
          <DialogTitle>Seleccionar producto</DialogTitle>
          <DialogDescription>
            Busca por nombre y reconoce el producto por su imagen. Después elegirás o propondrás una variante.
          </DialogDescription>

          <Input
            aria-label="Buscar producto"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Buscar productos…"
          />

          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 my-4 min-h-32">
            {isLoading ? (
              Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="border border-[var(--color-border)] rounded-xl p-3 animate-pulse">
                  <div className="w-full h-28 bg-[var(--color-border)] rounded-lg mb-2" />
                  <div className="h-3 bg-[var(--color-border)] rounded w-3/4 mb-1.5" />
                  <div className="h-3 bg-[var(--color-border)] rounded w-1/2" />
                </div>
              ))
            ) : isError ? (
              <p role="alert" className="col-span-full text-center text-[var(--color-error)] py-10">
                No se pudo cargar el catálogo.
              </p>
            ) : !data?.items?.length ? (
              <div className="col-span-full flex flex-col items-center gap-2 py-12 text-[var(--color-text-muted)]">
                <Search size={32} className="opacity-30" />
                <p className="text-sm">No hay resultados para esta búsqueda.</p>
              </div>
            ) : (
              data.items.map(p => (
                <button
                  type="button"
                  key={p._id}
                  onClick={() => { onSelect(p); setOpen(false) }}
                  className="text-left p-3 border border-[var(--color-border)] rounded-xl hover:border-[var(--color-action)] hover:shadow-[var(--shadow-md)] bg-[var(--color-surface)] transition-all group"
                >
                  {p.imagenes?.[0]
                    ? <img src={p.imagenes[0]} alt="" className="w-full h-28 object-contain rounded-lg bg-[var(--color-background)]" />
                    : <div className="h-28 grid place-items-center rounded-lg bg-[var(--color-background)] text-[var(--color-text-muted)]">
                        <ImageIcon size={24} />
                      </div>
                  }
                  <p className="font-semibold text-sm mt-2 group-hover:text-[var(--color-action)] transition-colors line-clamp-2">
                    {p.nombre}
                  </p>
                  <p className="text-xs font-mono text-[var(--color-text-muted)] mt-0.5">{p.sku}</p>
                </button>
              ))
            )}
          </div>

          <div className="flex gap-3 justify-center items-center border-t border-[var(--color-border)] pt-4">
            <Button type="button" variant="secondary" disabled={page === 1 || isLoading} onClick={() => setPage(p => p - 1)}>
              Anterior
            </Button>
            <span className="text-sm text-[var(--color-text-secondary)]">{page} / {data?.total_pages || 1}</span>
            <Button type="button" variant="secondary" disabled={isLoading || page >= (data?.total_pages || 1)} onClick={() => setPage(p => p + 1)}>
              Siguiente
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
