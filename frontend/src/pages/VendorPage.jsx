import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getVendorStats, getVendorOrders } from '../api/vendor'
import { getNotifications, markAllAsRead } from '../api/notifications'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { formatQ, formatDate } from '../lib/utils'
import { CatalogRequestsSection } from '../components/vendor/CatalogRequestsSection'
import { VendorOffers } from '../components/vendor/VendorOffers'
import { orderStateLabel } from './OrderWorkspacePage'

export default function VendorPage() {
  const navigate=useNavigate()
  const [params,setParams]=useSearchParams()
  const tab=params.get('tab')||'orders'
  const [page,setPage]=useState(1)
  const cache=useQueryClient()
  const {data:stats,error}=useQuery({queryKey:['vendor-stats'],queryFn:()=>getVendorStats().then(r=>r.data),retry:false})
  const {data:orders,isLoading}=useQuery({queryKey:['vendor-orders',page],queryFn:()=>getVendorOrders(page,20).then(r=>r.data),enabled:tab==='orders'})
  const {data:notifs=[]}=useQuery({queryKey:['vendor-notifications'],queryFn:()=>getNotifications().then(r=>r.data),enabled:tab==='notifications'})
  return <main className="max-w-6xl mx-auto p-6 space-y-6">
    <header><h1 className="text-2xl font-bold">Panel de vendedor</h1><p>{stats?.nombre_comercial}</p></header>
    {error ? <p role="alert">{error.response?.data?.detail||'No se pudo cargar el perfil.'}</p> : <>
      <div className="grid sm:grid-cols-3 gap-4">{[['Mis pedidos',stats?.total_pedidos],['Ingresos',stats?formatQ(stats.ingresos_totales):'—'],['Por preparar',stats?.pendientes]].map(([label,value])=><div key={label} className="border rounded-lg p-4 bg-[var(--color-surface)]"><p>{label}</p><strong className="text-2xl">{value??'—'}</strong></div>)}</div>
      <nav className="flex flex-wrap gap-2 border-b pb-3">{[['orders','Mis pedidos'],['offers','Mis ofertas'],['requests','Solicitudes de catálogo'],['notifications','Notificaciones']].map(([key,label])=><Button key={key} variant={tab===key?'primary':'secondary'} onClick={()=>setParams({tab:key})}>{label}</Button>)}</nav>
      {tab==='offers'&&<VendorOffers/>}
      {tab==='requests'&&<CatalogRequestsSection/>}
      {tab==='orders'&&<section className="space-y-4"><h2 className="text-xl font-semibold">Mis pedidos</h2><p>Abre un pedido para preparar tus productos, registrar envíos parciales y confirmar sus entregas.</p>
        <div className="overflow-x-auto border rounded-lg"><table className="w-full text-sm"><thead><tr className="text-left">{['Pedido','Fecha','Comprador','Mis productos','Mi subtotal','Estado'].map(h=><th key={h} className="p-3">{h}</th>)}</tr></thead><tbody>{isLoading?<tr><td colSpan={6} className="p-4">Cargando…</td></tr>:orders?.items.map(p=><tr key={p.pedido_vendedor_id} role="link" tabIndex={0} onClick={()=>navigate('/vendor/orders/'+p.id)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();navigate('/vendor/orders/'+p.id)}}} className="border-t hover:bg-[var(--color-surface)] cursor-pointer focus-visible:outline-2 focus-visible:outline-[var(--color-action)]"><td className="p-3"><Button variant="link" asChild><Link to={'/vendor/orders/'+p.id}>Abrir #{p.id}</Link></Button></td><td className="p-3">{formatDate(p.fecha)}</td><td className="p-3">{p.comprador?.nombre}</td><td className="p-3">{p.mis_lineas.map(l=>l.producto_nombre+' × '+l.cantidad).join(', ')}</td><td className="p-3">{formatQ(p.subtotal_mis_productos)}</td><td className="p-3"><Badge>{orderStateLabel(p.estado)}</Badge></td></tr>)}</tbody></table></div>
        {!isLoading&&!orders?.items.length&&<p>No tienes pedidos.</p>}<div className="flex justify-center gap-3"><Button variant="secondary" disabled={page===1} onClick={()=>setPage(p=>p-1)}>Anterior</Button><span>{page} / {orders?.total_pages||1}</span><Button variant="secondary" disabled={page>=(orders?.total_pages||1)} onClick={()=>setPage(p=>p+1)}>Siguiente</Button></div>
      </section>}
      {tab==='notifications'&&<section className="space-y-3"><Button variant="secondary" onClick={async()=>{await markAllAsRead();cache.invalidateQueries({queryKey:['vendor-notifications']});cache.invalidateQueries({queryKey:['notif-count']})}}>Marcar como leídas</Button>{notifs.map(n=><article key={n.id} className="border rounded-lg p-4"><strong>{n.titulo}</strong><p>{n.mensaje}</p><small>{formatDate(n.fecha)}</small></article>)}{!notifs.length&&<p>Sin notificaciones.</p>}</section>}
    </>}
  </main>
}
