import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import api from '../../api/client'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { formatQ } from '../../lib/utils'

export function VendorOffers() {
  const [search,setSearch]=useState(''); const [page,setPage]=useState(1); const [state,setState]=useState('todos')
  const {data,isLoading,isError}=useQuery({queryKey:['vendor-offers',search,page,state],queryFn:()=>api.get('/vendor/offers',{params:{q:search,page,...(state!=='todos'&&{estado:state})}}).then(r=>r.data)})
  return <section className="space-y-4"><h2 className="text-xl font-semibold">Mis productos y ofertas</h2><p>Consulta cada variante y administra tu precio y existencias. Los productos nuevos requieren aprobación.</p>
    <div className="flex gap-3"><Input aria-label="Buscar mis ofertas" placeholder="Buscar producto o SKU…" value={search} onChange={e=>{setSearch(e.target.value);setPage(1)}}/><Select value={state} onValueChange={v=>{setState(v);setPage(1)}}><SelectTrigger className="w-48"><SelectValue/></SelectTrigger><SelectContent>{['todos','activa','pausada','descontinuada','borrador'].map(s=><SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent></Select></div>
    {isLoading?<p>Cargando…</p>:isError?<p role="alert">No se pudieron cargar tus ofertas.</p>:<div className="grid md:grid-cols-2 gap-3">{data?.items.map(o=><Link className="flex gap-4 border p-4 rounded-lg bg-[var(--color-surface)] hover:border-[var(--color-action)]" key={o.id} to={`/vendor/offers/${o.id}`}>
      {o.imagen && <img alt="" src={o.imagen} className="w-20 h-20 object-contain"/>}<div><h3 className="font-semibold">{o.producto_nombre}</h3><p className="text-sm">{Object.entries(o.atributos).map(([k,v])=>`${k}: ${v}`).join(' · ')||'Variante predeterminada'}</p><p className="text-xs font-mono">{o.sku}</p><p>{formatQ(o.precio)} · {o.stock} disponibles · {o.estado}</p>{o.producto_estado!=='activo'&&<p className="text-sm text-[var(--color-error)]">Producto {o.producto_estado}: no visible en catálogo.</p>}</div></Link>)}</div>}
    {!isLoading&&!data?.items.length&&<p>No hay ofertas con estos filtros.</p>}<div className="flex justify-center gap-3"><Button variant="secondary" disabled={page===1} onClick={()=>setPage(p=>p-1)}>Anterior</Button><span>{page} / {data?.total_pages||1}</span><Button variant="secondary" disabled={page>=(data?.total_pages||1)} onClick={()=>setPage(p=>p+1)}>Siguiente</Button></div>
  </section>
}

function OfferForm({offer}) {
  const [price,setPrice]=useState(offer.precio); const [stock,setStock]=useState(offer.existencias); const [state,setState]=useState(offer.estado)
  const cache=useQueryClient()
  const mutation=useMutation({mutationFn:()=>api.patch(`/vendor/offers/${offer.id}`,{precio:Number(price),stock:Number(stock),estado:state,version:offer.version}),onSuccess:()=>{toast.success('Oferta actualizada con historial.');cache.invalidateQueries({queryKey:['vendor-offers']});cache.invalidateQueries({queryKey:['vendor-offer']})},onError:e=>toast.error(e.response?.data?.detail||'No se pudo guardar.')})
  const editable=['activa','pausada'].includes(offer.estado)
  return <form className="space-y-5" onSubmit={e=>{e.preventDefault();mutation.mutate()}}><div className="flex gap-5 items-center">{offer.imagen&&<img alt="" src={offer.imagen} className="w-28 h-28 object-contain"/>}<div><h1 className="text-2xl font-bold">{offer.producto_nombre}</h1><p>{Object.entries(offer.atributos).map(([k,v])=>`${k}: ${v}`).join(' · ')||'Variante predeterminada'}</p><p className="font-mono text-sm">{offer.sku}</p></div></div><div className="grid sm:grid-cols-3 gap-4"><div><Label>Precio (GTQ)</Label><Input required disabled={!editable} type="number" min="0.01" step="0.01" value={price} onChange={e=>setPrice(e.target.value)}/></div><div><Label>Existencias totales actuales</Label><Input required disabled={!editable} type="number" min={offer.reservado} max="2147483647" step="1" value={stock} onChange={e=>setStock(e.target.value)}/><p className="text-xs">Reservadas: {offer.reservado} · Disponibles actuales: {offer.stock}</p></div><div><Label>Estado de mi oferta</Label><Select disabled={!editable} value={state} onValueChange={setState}><SelectTrigger><SelectValue/></SelectTrigger><SelectContent>{['activa','pausada',...(!editable?[offer.estado]:[])].map(s=><SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent></Select></div></div><p className="text-sm">Las existencias son el saldo total, no una cantidad para sumar. Para agregar 10 a un saldo de 20, escribe 30. El precio y el inventario conservarán historial.</p>{editable?<Button loading={mutation.isPending} type="submit">Guardar cambios</Button>:<p>Esta oferta requiere revisión del administrador para volver a publicarse.</p>}</form>
}

export default function VendorOfferPage(){
  const {id}=useParams(); const {data,isLoading,isError,refetch}=useQuery({queryKey:['vendor-offer',id],queryFn:()=>api.get('/vendor/offers',{params:{oferta_id:id}}).then(r=>r.data.items[0])})
  return <main className="max-w-5xl mx-auto p-6 space-y-6"><Link to="/vendor?tab=offers">← Mis ofertas</Link>{isLoading?<p>Cargando…</p>:isError||!data?<p role="alert">Oferta no encontrada o sin permiso.</p>:<><OfferForm key={`${data.id}-${data.version}`} offer={data}/><Button variant="secondary" onClick={()=>refetch()}>Recargar datos actuales</Button></>}</main>
}
