import {useState} from 'react'
import {Link,useLocation,useParams} from 'react-router-dom'
import {useQuery,useMutation,useQueryClient} from '@tanstack/react-query'
import {toast} from 'sonner'
import api from '../api/client'
import {Button} from '../components/ui/button'
import {Badge} from '../components/ui/badge'
import {formatQ,formatDate} from '../lib/utils'

export const requestType = type => ({producto_nuevo:'Producto nuevo',variante_nueva:'Variante con oferta inicial',oferta_existente:'Oferta existente'}[type]||type)

export default function CatalogRequestPage(){
  const {id}=useParams();const {pathname}=useLocation();const admin=pathname.startsWith('/admin')
  const prefix=admin?'admin':'vendor';const [note,setNote]=useState('');const cache=useQueryClient()
  const {data:r,isLoading,isError}=useQuery({queryKey:['catalog-request',prefix,id],queryFn:()=>api.get(`/${prefix}/catalog-requests/${id}`).then(res=>res.data)})
  const action=useMutation({mutationFn:kind=>kind==='cancel'?api.patch(`/vendor/catalog-requests/${id}/cancel`):api.post(`/admin/catalog-requests/${id}/${kind}`,{observaciones:note}),onSuccess:()=>{toast.success('Solicitud actualizada.');cache.invalidateQueries({queryKey:['catalog-request']});cache.invalidateQueries({queryKey:['admin-catalog-requests']});cache.invalidateQueries({queryKey:['vendor-catalog-requests']});cache.invalidateQueries({queryKey:['vendor-offers']})},onError:e=>toast.error(e.response?.data?.detail||'No se pudo actualizar.')})
  return <main className="max-w-5xl mx-auto p-6 space-y-6"><Link to={admin?'/admin?section=requests':'/vendor?tab=requests'}>← Solicitudes</Link>
    {isLoading?<p>Cargando solicitud…</p>:isError||!r?<p role="alert">No se encontró la solicitud o no tienes permiso.</p>:<>
      <header className="flex justify-between gap-4"><div><h1 className="text-2xl font-bold">Solicitud #{r.id}</h1><p>{requestType(r.tipo)} · {formatDate(r.fecha_creacion)}</p></div><Badge>{r.estado}</Badge></header>
      <section className="border rounded-xl p-5 bg-[var(--color-surface)] space-y-4"><h2 className="text-xl font-semibold">{r.nombre||r.producto_nombre}</h2><div className="grid sm:grid-cols-3 gap-4"><div><small>Vendedor</small><p>{r.vendedor_nombre}</p></div><div><small>Precio de la oferta</small><p>{formatQ(r.precio_propuesto)}</p></div><div><small>Stock inicial</small><p>{r.stock_propuesto}</p></div></div>{r.descripcion&&<p>{r.descripcion}</p>}<p>Categorías: {r.categorias.map(c=>c.nombre).join(', ')||'Las del producto existente'}</p><p className="text-xs">SKU automático al aprobar.</p></section>
      <section className="border rounded-xl p-5 space-y-3"><h2 className="font-semibold">Atributos propuestos / variante</h2><dl className="grid sm:grid-cols-2 gap-3">{Object.entries(r.tipo==='oferta_existente'?r.variante_atributos:r.atributos).map(([k,v])=><div key={k}><dt className="text-sm text-[var(--color-text-muted)]">{k}</dt><dd>{String(v)}</dd></div>)}</dl>{!Object.keys(r.atributos||{}).length&&!Object.keys(r.variante_atributos||{}).length&&<p>Variante predeterminada sin atributos diferenciadores.</p>}</section>
      {!!r.imagenes.length&&<section className="grid grid-cols-2 md:grid-cols-4 gap-4">{r.imagenes.map(image=><img key={image.id} src={image.url} alt="Imagen propuesta" className="h-40 object-contain border rounded-lg w-full"/>)}</section>}
      <section className="space-y-3"><h2 className="font-semibold">Observaciones</h2><p>Vendedor: {r.observaciones_vendedor||'Sin observaciones'}</p><p>Administrador: {r.observaciones_admin||'Sin observaciones'}</p>{r.estado==='pendiente'&&admin&&<><textarea aria-label="Observaciones del administrador" className="w-full p-3 border rounded-lg bg-[var(--color-surface)]" rows={4} value={note} onChange={e=>setNote(e.target.value)} placeholder="Motivo de aprobación o rechazo…"/><div className="flex gap-3"><Button disabled={action.isPending} onClick={()=>action.mutate('approve')}>Aprobar y publicar</Button><Button variant="destructive" disabled={action.isPending} onClick={()=>{if(!note.trim())return toast.error('Indica un motivo de rechazo.');action.mutate('reject')}}>Rechazar</Button></div></>}{r.estado==='pendiente'&&!admin&&<Button variant="secondary" disabled={action.isPending} onClick={()=>action.mutate('cancel')}>Cancelar solicitud</Button>}</section>
      {r.estado==='aprobada'&&<p>Publicado: oferta #{r.oferta_id_resultado}. <Link className="text-[var(--color-action)]" to={admin?`/admin/products/${r.producto_ref_resultado}`:`/vendor/offers/${r.oferta_id_resultado}`}>Abrir resultado →</Link></p>}
    </>}
  </main>
}
