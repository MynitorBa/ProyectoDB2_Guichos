import { useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import api from '../api/client'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Badge } from '../components/ui/badge'
import { formatQ, formatDatetime } from '../lib/utils'

export const orderStateLabel = state => ({preparando:'En preparación', enviado_parcial:'Envío parcial', entregado_parcial:'Entrega parcial'}[state] || state?.replaceAll('_',' '))

function apiErrorMessage(error, fallback) {
  const detail = error.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(item => item.msg || 'Dato inválido.').join(' ')
  if (detail && typeof detail.message === 'string') return detail.message
  return fallback
}

function Part({ part, orderId, canManage, terminal }) {
  const [amounts, setAmounts] = useState({})
  const [reference, setReference] = useState('')
  const queryClient = useQueryClient()
  const action = useMutation({
    mutationFn: ({ url, body }) => api.post(`/fulfillment/orders/${orderId}/${url}`, body),
    onSuccess: () => {
      toast.success('Avance del pedido actualizado.'); setAmounts({}); setReference('')
      for (const key of ['fulfillment', 'order', 'orders', 'vendor-orders', 'vendor-stats', 'admin-orders', 'admin-sales']) queryClient.invalidateQueries({queryKey:[key]})
    },
    onError: e => toast.error(apiErrorMessage(e, 'No se pudo registrar el cambio.')),
  })
  function send() {
    const lineas = part.lineas.filter(l => Number(amounts[l.id]) > 0).map(l => ({pedido_linea_id:l.id, cantidad:Number(amounts[l.id])}))
    if (!lineas.length) return toast.error('Indica al menos una cantidad para enviar.')
    if (lineas.some(line => !Number.isSafeInteger(line.cantidad))) return toast.error('Las cantidades deben ser números enteros.')
    action.mutate({url:`parts/${part.id}/shipments`, body:{lineas, referencia:reference || null}})
  }
  const editable = canManage && !terminal && !['cancelado','reembolsado'].includes(part.estado)
  return <section className="border rounded-xl bg-[var(--color-surface)] p-5 space-y-4">
    <header className="flex flex-wrap justify-between gap-3"><div><h2 className="text-xl font-semibold">{part.vendedor_nombre}</h2><p className="text-xs">Subpedido #{part.id} · {formatQ(part.subtotal)}</p></div><Badge>{orderStateLabel(part.estado)}</Badge></header>
    {editable && part.estado === 'confirmado' && <Button loading={action.isPending} onClick={() => action.mutate({url:`parts/${part.id}/prepare`})}>Comenzar preparación</Button>}
    <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="text-left border-b">{['Producto / variante (SKU)','Precio','Pedido','Enviado','Entregado','Por enviar', ...(editable?['Enviar ahora']:[])].map(h=><th className="p-2" key={h}>{h}</th>)}</tr></thead><tbody>{part.lineas.map(l=><tr key={l.id} className="border-b"><td className="p-2"><p className="font-semibold">{l.producto_nombre}</p><p className="text-xs font-mono">{l.sku}</p></td><td className="p-2">{formatQ(l.precio)}</td><td className="p-2">{l.cantidad}</td><td className="p-2">{l.enviado}</td><td className="p-2">{l.entregado}</td><td className="p-2">{l.pendiente_envio}</td>{editable && <td className="p-2"><Input aria-label={`Enviar ${l.producto_nombre}`} className="w-24" type="number" inputMode="numeric" min="0" max={l.pendiente_envio} step="1" disabled={!l.pendiente_envio || part.estado==='pendiente'} value={amounts[l.id] ?? ''} placeholder="0" onKeyDown={e=>{if(['.','e','E','+','-',','].includes(e.key))e.preventDefault()}} onChange={e=>{const value=e.target.value;if(value===''||/^\d+$/.test(value))setAmounts({...amounts,[l.id]:value})}} /></td>}</tr>)}</tbody></table></div>
    {editable && part.lineas.some(l=>l.pendiente_envio>0) && part.estado!=='pendiente' && <div className="flex flex-wrap gap-3"><Input className="max-w-sm" aria-label="Referencia de envío" placeholder="Guía o referencia de envío (opcional)" maxLength={120} value={reference} onChange={e=>setReference(e.target.value)} /><Button loading={action.isPending} onClick={send}>Registrar envío seleccionado</Button></div>}
    <h3 className="font-semibold">Envíos de este vendedor</h3>
    {!part.envios.length && <p className="text-sm text-[var(--color-text-muted)]">Todavía no hay envíos.</p>}
    {part.envios.map(s=><article key={s.id} className="p-3 rounded border space-y-2"><div className="flex justify-between gap-3"><strong>Envío #{s.id}</strong><Badge>{orderStateLabel(s.estado)}</Badge></div><p className="text-sm">{s.referencia || 'Sin referencia'} · {s.fecha_envio ? formatDatetime(s.fecha_envio) : 'Fecha histórica no registrada'}</p><ul className="text-sm">{s.lineas.map(l=><li key={l.pedido_linea_id}>{part.lineas.find(p=>p.id===l.pedido_linea_id)?.producto_nombre} — {l.cantidad} unidades</li>)}</ul>{s.fecha_entrega && <p className="text-xs">Entregado: {formatDatetime(s.fecha_entrega)}</p>}{editable && s.estado==='enviado' && <Button size="sm" loading={action.isPending} onClick={()=>action.mutate({url:`shipments/${s.id}/deliver`})}>Confirmar entrega de este envío</Button>}</article>)}
  </section>
}

export function FulfillmentPanel({ orderId }) {
  const cache = useQueryClient()
  const statusAction = useMutation({mutationFn: estado => api.patch(`/admin/orders/${orderId}/status`,{estado}),onSuccess:()=>{cache.invalidateQueries({queryKey:['fulfillment']});cache.invalidateQueries({queryKey:['order']});cache.invalidateQueries({queryKey:['admin-orders']});toast.success('Pedido actualizado.')},onError:e=>toast.error(apiErrorMessage(e,'No se pudo actualizar.'))})
  const {data, isLoading, isError} = useQuery({queryKey:['fulfillment',String(orderId)], refetchInterval:15000, queryFn:()=>api.get(`/fulfillment/orders/${orderId}`).then(r=>r.data)})
  if(isLoading) return <p>Cargando avance de entrega…</p>
  if(isError) return <p role="alert">No se pudo cargar el pedido o no tienes acceso.</p>
  return <div className="space-y-5"><div className="flex items-start justify-between flex-wrap gap-4"><div><h1 className="text-2xl font-bold">Pedido #{data.id}</h1><p>{data.comprador.nombre} · {formatDatetime(data.fecha)}</p><p className="text-sm">{data.vista_vendedor?'Subtotal de tus productos':'Total de la compra'}: {formatQ(data.total)}</p></div><Badge>{orderStateLabel(data.estado)}</Badge></div>
    {data.direccion && <section className="border rounded-lg p-4"><h2 className="font-semibold">Dirección de entrega del pedido</h2><p>{data.direccion.receptor_nombre} · {data.direccion.receptor_telefono}</p><p>{[data.direccion.linea1,data.direccion.linea2,data.direccion.municipio,data.direccion.departamento].filter(Boolean).join(', ')}</p></section>}
    <p className="text-sm text-[var(--color-text-secondary)]">El pedido se completa cuando se entregan todas las unidades de todos los vendedores.</p>
    {data.puede_confirmar && <Button loading={statusAction.isPending} onClick={()=>statusAction.mutate('confirmado')}>Confirmar pedido pendiente</Button>}
    {data.puede_cancelar && <Button variant="destructive" loading={statusAction.isPending} onClick={()=>{if(window.confirm('¿Cancelar antes del envío y reponer las existencias? El reembolso simulado se registra por separado.'))statusAction.mutate('cancelado')}}>Cancelar pedido sin envíos</Button>}
    {data.puede_reembolsar && <Button variant="secondary" loading={statusAction.isPending} onClick={()=>statusAction.mutate('reembolsado')}>Registrar reembolso simulado</Button>}
    {!data.vista_vendedor && <section className="border rounded-lg p-4 space-y-2"><h2 className="font-semibold">Resumen comercial</h2><p>Subtotal: {formatQ(data.subtotal)} · IVA: {formatQ(data.impuestos)} · Total: {formatQ(data.total)}</p>{data.pagos.map((p,i)=><p key={i} className="text-sm">Pago {p.estado}: {formatQ(p.monto)} · {p.referencia}</p>)}</section>}
    {data.subpedidos.map(part=><Part key={part.id} part={part} orderId={orderId} canManage={data.puede_gestionar} terminal={['cancelado','reembolsado'].includes(data.estado)} />)}
  </div>
}

export default function OrderWorkspacePage(){
  const {id}=useParams(); const {pathname}=useLocation()
  const back=pathname.startsWith('/admin')?`/admin?section=${pathname.includes('/sales/')?'sales':'orders'}`:'/vendor'
  return <main className="max-w-6xl mx-auto p-6 space-y-6"><Link to={back} className="text-[var(--color-action)]">← Volver al listado</Link>{pathname.includes('/sales/') && <h1 className="text-2xl font-bold">Detalle de venta</h1>}<FulfillmentPanel orderId={id}/></main>
}
