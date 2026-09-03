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
  useEffect(() => { const timer = setTimeout(() => { setQ(search); setPage(1) }, 250); return () => clearTimeout(timer) }, [search])
  const { data, isLoading, isError } = useQuery({
    queryKey: ['product-picker', q, page], enabled: open,
    queryFn: () => getProducts({ q, page, page_size: 12, orden: 'nombre_asc' }).then(r => r.data),
  })
  return <div className="space-y-2">
    <Button type="button" variant="secondary" onClick={() => setOpen(true)}><Search size={16} />{value ? 'Cambiar producto' : 'Buscar y seleccionar producto'}</Button>
    {value && <p className="font-semibold">{value.nombre} <span className="text-xs font-mono">{value.sku}</span></p>}
    <Dialog open={open} onOpenChange={setOpen}><DialogContent className="max-w-4xl"><DialogTitle>Seleccionar producto</DialogTitle><DialogDescription>Busca por nombre y reconoce el producto por su imagen. Después elegirás o propondrás una variante.</DialogDescription>
      <Input aria-label="Buscar producto" value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar productos…" />
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 my-4 min-h-32">
        {isLoading ? <p>Cargando productos…</p> : isError ? <p role="alert">No se pudo cargar el catálogo.</p> : !data?.items?.length ? <p>No hay resultados.</p> : data.items.map(p => <button type="button" key={p._id} onClick={() => { onSelect(p); setOpen(false) }} className="text-left p-3 border rounded-lg hover:border-[var(--color-action)] bg-[var(--color-surface)]">
          {p.imagenes?.[0] ? <img src={p.imagenes[0]} alt="" className="w-full h-28 object-contain" /> : <div className="h-28 grid place-items-center"><ImageIcon /></div>}
          <p className="font-semibold text-sm mt-2">{p.nombre}</p><p className="text-xs font-mono text-[var(--color-text-muted)]">{p.sku}</p>
        </button>)}
      </div>
      <div className="flex gap-3 justify-center items-center"><Button type="button" variant="secondary" disabled={page===1 || isLoading} onClick={() => setPage(p=>p-1)}>Anterior</Button><span>{page} / {data?.total_pages || 1}</span><Button type="button" variant="secondary" disabled={isLoading || page >= (data?.total_pages || 1)} onClick={() => setPage(p=>p+1)}>Siguiente</Button></div>
    </DialogContent></Dialog>
  </div>
}
