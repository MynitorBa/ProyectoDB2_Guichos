import {useState} from 'react'
import {Link,useParams} from 'react-router-dom'
import {useQuery,useMutation,useQueryClient} from '@tanstack/react-query'
import {toast} from 'sonner'
import api from '../api/client'
import {getAdminVendors,setVendorProfile,setTiendayaVendor} from '../api/admin'
import {Button} from '../components/ui/button'
import {Input} from '../components/ui/input'
import {Label} from '../components/ui/label'
import {Select,SelectContent,SelectItem,SelectTrigger,SelectValue} from '../components/ui/select'
import {formatQ,formatDate} from '../lib/utils'
import {orderStateLabel} from './OrderWorkspacePage'

export function AdminVendorsSection(){
  const [search,setSearch]=useState('');const {data=[],isLoading,isError}=useQuery({queryKey:['admin-vendors'],queryFn:()=>getAdminVendors().then(r=>r.data)})
  return <section className="space-y-4"><Input aria-label="Buscar vendedor" placeholder="Buscar negocio, persona o correo…" value={search} onChange={e=>setSearch(e.target.value)}/>{isLoading?<p>Cargando…</p>:isError?<p>No se pudieron consultar los vendedores.</p>:data.filter(v=>[v.nombre_comercial,v.nombre_completo,v.email].join(' ').toLowerCase().includes(search.toLowerCase())).map(v=><Link key={v.usuario_id} to={v.vendedor_id?`/admin/vendors/${v.vendedor_id}`:`/admin/users/${v.usuario_id}`} className="block border rounded-xl p-4 bg-[var(--color-surface)]"><strong>{v.nombre_comercial||v.nombre_completo}</strong><p>{v.email} · {v.nit||'Sin perfil comercial'} · {v.estado_verificacion}</p>{v.es_tiendaya&&<p>Vendedor propio de TiendaYa</p>}</Link>)}</section>
}

function Profile({vendor}){
  const [name,setName]=useState(vendor.nombre_comercial);const [nit,setNit]=useState(vendor.nit);const cache=useQueryClient()
  const mutation=useMutation({mutationFn:()=>setVendorProfile(vendor.usuario_id,{nombre_comercial:name,nit}),onSuccess:()=>{toast.success('Perfil actualizado.');cache.invalidateQueries({queryKey:['admin-vendors']});cache.invalidateQueries({queryKey:['admin-vendor']})},onError:e=>toast.error(e.response?.data?.detail||'No se pudo guardar.')})
  const mark=useMutation({mutationFn:()=>setTiendayaVendor(vendor.id),onSuccess:()=>{cache.invalidateQueries({queryKey:['admin-vendors']});cache.invalidateQueries({queryKey:['admin-vendor']})},onError:e=>toast.error(e.response?.data?.detail||'No se pudo cambiar la marca.')})
  return <section className="border rounded-xl p-5 space-y-4"><form onSubmit={e=>{e.preventDefault();mutation.mutate()}} className="grid sm:grid-cols-3 gap-4 items-end"><div><Label>Nombre comercial</Label><Input required value={name} onChange={e=>setName(e.target.value)}/></div><div><Label>NIT</Label><Input required value={nit} onChange={e=>setNit(e.target.value)}/></div><Button type="submit" loading={mutation.isPending}>Guardar perfil</Button></form><p>Verificación: {vendor.estado_verificacion}</p><Button variant="secondary" loading={mark.isPending} onClick={()=>mark.mutate()}>{vendor.es_tiendaya?'Quitar marca TiendaYa':'Marcar como vendedor TiendaYa'}</Button></section>
}

export default function AdminVendorPage(){
  const {id}=useParams();const [ordersPage,setOrdersPage]=useState(1);const [offersPage,setOffersPage]=useState(1);const [state,setState]=useState('todos')
  const {data:v,isLoading,isError}=useQuery({queryKey:['admin-vendor',id,ordersPage,offersPage,state],queryFn:()=>api.get(`/admin/vendors/${id}`,{params:{orders_page:ordersPage,offers_page:offersPage,...(state!=='todos'&&{estado:state})}}).then(r=>r.data)})
  return <main className="max-w-6xl mx-auto p-6 space-y-5"><Link to="/admin?section=vendors">← Vendedores</Link>{isLoading?<p>Cargando…</p>:isError?<p role="alert">No se pudo cargar el vendedor.</p>:<><h1 className="text-2xl font-bold">{v.nombre_comercial}</h1><Link to={`/admin/users/${v.usuario_id}`} className="text-[var(--color-action)]">Cuenta: {v.email}</Link><Profile key={v.id} vendor={v}/><section className="space-y-3"><h2 className="text-xl font-semibold">Pedidos del vendedor</h2><div className="flex flex-wrap gap-2">{Object.entries(v.pedidos_por_estado).map(([s,n])=><span className="border rounded px-3 py-2" key={s}>{orderStateLabel(s)}: {n}</span>)}</div><Select value={state} onValueChange={s=>{setState(s);setOrdersPage(1)}}><SelectTrigger className="w-56"><SelectValue/></SelectTrigger><SelectContent><SelectItem value="todos">Todos los estados</SelectItem>{Object.keys(v.pedidos_por_estado).map(s=><SelectItem key={s} value={s}>{orderStateLabel(s)}</SelectItem>)}</SelectContent></Select>{v.pedidos.map(p=><Link key={p.subpedido_id} to={`/admin/orders/${p.id}`} className="block p-3 border rounded-lg">Pedido #{p.id} · {formatDate(p.fecha)} · {orderStateLabel(p.estado)} · {formatQ(p.subtotal)}</Link>)}<div className="flex gap-3"><Button variant="secondary" disabled={ordersPage===1} onClick={()=>setOrdersPage(p=>p-1)}>Anterior</Button><span>{ordersPage} / {v.pedidos_pages}</span><Button variant="secondary" disabled={ordersPage>=v.pedidos_pages} onClick={()=>setOrdersPage(p=>p+1)}>Siguiente</Button></div></section><section className="space-y-3"><h2 className="text-xl font-semibold">Ofertas y productos</h2>{v.ofertas.map(o=><Link key={o.id} to={`/admin/products/${o.producto_ref}?tab=offers`} className="block p-3 border rounded-lg"><strong>{o.producto_nombre}</strong><p>{o.sku} · {o.estado} · {formatQ(o.precio)} · {o.stock} disponibles</p></Link>)}<div className="flex gap-3"><Button variant="secondary" disabled={offersPage===1} onClick={()=>setOffersPage(p=>p-1)}>Anterior</Button><span>{offersPage} / {v.ofertas_pages}</span><Button variant="secondary" disabled={offersPage>=v.ofertas_pages} onClick={()=>setOffersPage(p=>p+1)}>Siguiente</Button></div></section></>}</main>
}
