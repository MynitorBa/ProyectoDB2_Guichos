import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import ProductPicker from '../ProductPicker'
import { requestType } from '../../pages/CatalogRequestPage'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { FilePlus2, ImagePlus, Layers, Sparkles, X } from 'lucide-react'
import { toast } from 'sonner'

import {
  cancelCatalogRequest, deleteRequestImage, getCatalogRequests,
  proposeOffer, proposeProduct, proposeVariant, uploadRequestImage,
} from '../../api/vendor'
import { getCategories, getCategorySchema, getProduct, getProducts } from '../../api/products'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { Skeleton } from '../ui/skeleton'
import { formatDate, formatQ } from '../../lib/utils'

const STATUS = { pendiente: 'warning', aprobada: 'success', rechazada: 'error', cancelada: 'default' }

// Dialog para proponer un producto nuevo con categorías, atributos dinámicos por esquema, imágenes y oferta inicial
function ProductProposalDialog({ open, onOpenChange }) {
  const queryClient = useQueryClient()
  const fileRef = useRef(null)
  const [form, setForm] = useState({
    nombre: '', descripcion: '', categoria_slugs: [], atributos: {},
    imagenes: [], precio: '', stock: '', observaciones: '',
  })
  const [uploading, setUploading] = useState(false)
  const { data: categories = [] } = useQuery({
    queryKey: ['categories'], queryFn: () => getCategories().then(r => r.data),
  })
  const schemaQueries = useQueries({
    queries: form.categoria_slugs.map(slug => ({
      queryKey: ['category-schema', slug],
      queryFn: () => getCategorySchema(slug).then(r => r.data),
      enabled: !!slug,
      staleTime: 5 * 60 * 1000,
    })),
  })
  const attributeSections = form.categoria_slugs.map((slug, index) => ({
    slug,
    categoryName: categories.find(category => category.slug === slug)?.nombre || slug,
    fields: schemaQueries[index]?.data?.atributos || [],
  })).filter(section => section.fields.length > 0)
  const mutation = useMutation({
    mutationFn: proposeProduct,
    onSuccess: () => {
      toast.success('Propuesta enviada para revisión.')
      queryClient.invalidateQueries({ queryKey: ['vendor-catalog-requests'] })
      onOpenChange(false)
      setForm({ nombre: '', descripcion: '', categoria_slugs: [], atributos: {}, imagenes: [], precio: '', stock: '', observaciones: '' })
    },
    onError: err => toast.error(err?.response?.data?.detail || 'No se pudo enviar la propuesta.'),
  })

  async function upload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const { data } = await uploadRequestImage(file)
      setForm(p => ({ ...p, imagenes: [...p.imagenes, data] }))
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'No se pudo subir la imagen.')
    } finally {
      setUploading(false); e.target.value = ''
    }
  }

  async function removeImage(image) {
    try { await deleteRequestImage(image.id) } catch { /* la API protege imágenes ya asociadas */ }
    setForm(p => ({ ...p, imagenes: p.imagenes.filter(i => i.id !== image.id) }))
  }

  function submit(e) {
    e.preventDefault()
    if (!form.nombre || !form.precio || form.categoria_slugs.length === 0) {
      return toast.error('Completa nombre, precio y al menos una categoría.')
    }
    const missing = attributeSections.flatMap(section => section.fields)
      .filter(field => field.requerido && (form.atributos[field.nombre] === undefined || form.atributos[field.nombre] === null || form.atributos[field.nombre] === ''))
    if (missing.length) return toast.error(`Completa: ${missing.map(field => field.etiqueta).join(', ')}.`)
    const attributes = {}
    attributeSections.forEach(section => section.fields.forEach(field => {
      const value = form.atributos[field.nombre]
      if (value === undefined || value === null || value === '') return
      attributes[field.nombre] = field.tipo === 'number' ? Number(value) : value
    }))
    mutation.mutate({
      nombre: form.nombre, descripcion: form.descripcion || null,
      categoria_slugs: form.categoria_slugs, atributos: attributes,
      imagen_ids: form.imagenes.map(i => i.id),
      precio: Number(form.precio), stock: Number(form.stock) || 0,
      observaciones: form.observaciones || null,
    })
  }

  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="max-w-2xl">
      <DialogTitle>Proponer producto nuevo</DialogTitle>
      <DialogDescription>El producto y su oferta solo se publicarán cuando un administrador los apruebe.</DialogDescription>
      <form onSubmit={submit} className="space-y-4">
        <div><Label>Nombre *</Label><Input value={form.nombre} onChange={e => setForm(p => ({ ...p, nombre: e.target.value }))} /></div>
        <div><Label>Descripción</Label><textarea rows={3} value={form.descripcion} onChange={e => setForm(p => ({ ...p, descripcion: e.target.value }))} className="w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm" /></div>
        <div>
          <Label>Categorías * <span className="font-normal text-xs">(la primera será principal)</span></Label>
          <div className="flex flex-wrap gap-1.5 my-2">{form.categoria_slugs.map((slug, index) => <Badge key={slug} variant="action">{index === 0 ? 'Principal · ' : ''}{categories.find(c => c.slug === slug)?.nombre || slug}<button type="button" className="ml-1" onClick={() => setForm(p => ({ ...p, categoria_slugs: p.categoria_slugs.filter(s => s !== slug) }))}><X size={10} /></button></Badge>)}</div>
          <Select value="" onValueChange={slug => setForm(p => ({ ...p, categoria_slugs: [...p.categoria_slugs, slug] }))}>
            <SelectTrigger><SelectValue placeholder="Añadir categoría..." /></SelectTrigger>
            <SelectContent>{categories.filter(c => !form.categoria_slugs.includes(c.slug)).map(c => <SelectItem key={c.slug} value={c.slug}>{c.nombre}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        {attributeSections.map(section => <div key={section.slug} className="space-y-2 border border-[var(--color-border)] rounded-[var(--radius-md)] p-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">Atributos de {section.categoryName}</p>
          <div className="grid grid-cols-2 gap-3">{section.fields.map(attr => <div key={attr.nombre}>{attr.tipo === 'boolean' ? <label className="flex items-center gap-2 pt-5 cursor-pointer"><input type="checkbox" checked={!!form.atributos[attr.nombre]} onChange={e => setForm(p => ({ ...p, atributos: { ...p.atributos, [attr.nombre]: e.target.checked } }))} className="h-4 w-4 accent-[var(--color-action)]" /><span className="text-sm">{attr.etiqueta}{attr.requerido ? ' *' : ''}</span></label> : <><Label>{attr.etiqueta}{attr.requerido ? ' *' : ''}</Label><Input type={attr.tipo === 'number' ? 'number' : 'text'} placeholder={attr.placeholder || ''} value={form.atributos[attr.nombre] ?? ''} onChange={e => setForm(p => ({ ...p, atributos: { ...p.atributos, [attr.nombre]: e.target.value } }))} /></>}</div>)}</div>
        </div>)}
        <div className="grid grid-cols-2 gap-3"><div><Label>Precio inicial *</Label><Input type="number" min="0.01" step="0.01" value={form.precio} onChange={e => setForm(p => ({ ...p, precio: e.target.value }))} /></div><div><Label>Stock inicial *</Label><Input type="number" min="0" value={form.stock} onChange={e => setForm(p => ({ ...p, stock: e.target.value }))} /></div></div>
        <p className="text-xs text-[var(--color-text-muted)]">El SKU del producto y de la oferta se generará automáticamente al aprobar.</p>
        <div><div className="flex items-center justify-between"><Label>Imágenes del producto</Label><Button type="button" variant="secondary" size="sm" onClick={() => fileRef.current?.click()} loading={uploading}><ImagePlus size={13} />Agregar</Button></div><input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif" className="hidden" onChange={upload} /><div className="grid grid-cols-4 gap-2 mt-2">{form.imagenes.map(image => <div key={image.id} className="relative aspect-square border rounded overflow-hidden"><img src={image.url} className="w-full h-full object-cover" /><button type="button" onClick={() => removeImage(image)} className="absolute top-1 right-1 rounded-full bg-black/70 text-white p-1"><X size={11} /></button></div>)}</div></div>
        <div><Label>Comentario para el administrador</Label><textarea rows={2} value={form.observaciones} onChange={e => setForm(p => ({ ...p, observaciones: e.target.value }))} className="w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-background)] px-3 py-2 text-sm" /></div>
        <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>Cancelar</Button><Button type="submit" loading={mutation.isPending}>Enviar propuesta</Button></div>
      </form>
    </DialogContent>
  </Dialog>
}

// Dialog para solicitar una oferta sobre un producto ya existente, con precio y stock propios del vendedor
function OfferProposalDialog({ open, onOpenChange, variant = false }) {
  const queryClient = useQueryClient()
  const [product,setProduct]=useState(null)
  const [form,setForm]=useState({producto_variante_id:'',precio:'',stock:'',observaciones:''})
  const [attrs,setAttrs]=useState([{key:'',value:'',type:'string'}])
  const {data:selectedProduct}=useQuery({queryKey:['product-for-offer-request',product?._id],queryFn:()=>getProduct(product._id).then(r=>r.data),enabled:open&&!!product})
  const variants=selectedProduct?.variantes?.filter(v=>v.estado==='activa')||[]
  useEffect(()=>{
    if(!variant||!selectedProduct) return
    const inherited=Object.entries(selectedProduct.atributos||{}).map(([key,value])=>({
      key, value:String(value),
      type:typeof value==='number'?'number':typeof value==='boolean'?'boolean':'string',
    }))
    setAttrs(inherited.length?inherited:[{key:'',value:'',type:'string'}])
  },[variant,selectedProduct?._id])
  const mutation=useMutation({
    mutationFn: data => variant ? proposeVariant(data) : proposeOffer(data),
    onSuccess:()=>{toast.success('Solicitud enviada para aprobación.');queryClient.invalidateQueries({queryKey:['vendor-catalog-requests']});onOpenChange(false);setProduct(null);setForm({producto_variante_id:'',precio:'',stock:'',observaciones:''});setAttrs([{key:'',value:'',type:'string'}])},
    onError:e=>toast.error(e.response?.data?.detail||'No se pudo enviar la solicitud.'),
  })
  function submit(e){
    e.preventDefault()
    if(!product) return toast.error('Selecciona un producto.')
    const payload={producto_ref:product._id,precio:Number(form.precio),stock:Number(form.stock),observaciones:form.observaciones||null}
    if(variant){
      if(attrs.some(a=>!a.key.trim()||a.value===''||(a.type==='boolean'&&!['true','false'].includes(a.value)))) return toast.error('Completa cada atributo.')
      if(new Set(attrs.map(a=>a.key.trim().toLowerCase())).size!==attrs.length) return toast.error('No repitas atributos.')
      payload.atributos=Object.fromEntries(attrs.map(a=>[a.key,a.type==='number'?Number(a.value):a.type==='boolean'?a.value==='true':a.value]))
    }else{
      payload.producto_variante_id=Number(form.producto_variante_id||(variants.length===1?variants[0].variante_id:0))
      if(!payload.producto_variante_id) return toast.error('Selecciona una variante.')
    }
    mutation.mutate(payload)
  }
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-2xl"><DialogTitle>{variant?'Proponer variante y oferta':'Solicitar oferta'}</DialogTitle><DialogDescription>{variant?'Propones una nueva combinación y tu primera oferta. Ambas se publican al aprobar.':'Selecciona un producto y la variante exacta que vendes. Las imágenes pertenecen al producto.'}</DialogDescription>
    <form onSubmit={submit} className="space-y-4"><ProductPicker value={product} onSelect={p=>{setProduct(p);setForm(f=>({...f,producto_variante_id:''}));setAttrs([{key:'',value:'',type:'string'}])}}/>
      {product&&variant&&<section className="space-y-2"><Label>Atributos de la nueva variante</Label><p className="text-xs">Ejemplos: RAM = 32 GB, almacenamiento = 1 TB. No cambias los datos comunes del producto.</p>{attrs.map((a,i)=><div key={i} className="flex gap-2"><Input aria-label={'Atributo '+(i+1)} placeholder="Atributo" value={a.key} onChange={e=>setAttrs(rows=>rows.map((r,j)=>j===i?{...r,key:e.target.value}:r))}/><Input aria-label={'Valor '+(i+1)} placeholder={a.type==='boolean'?'true o false':'Valor'} type={a.type==='number'?'number':'text'} step="any" value={a.value} onChange={e=>setAttrs(rows=>rows.map((r,j)=>j===i?{...r,value:e.target.value}:r))}/><Select value={a.type} onValueChange={v=>setAttrs(rows=>rows.map((r,j)=>j===i?{...r,type:v,value:''}:r))}><SelectTrigger className="w-32"><SelectValue/></SelectTrigger><SelectContent><SelectItem value="string">Texto</SelectItem><SelectItem value="number">Número</SelectItem><SelectItem value="boolean">Booleano</SelectItem></SelectContent></Select><Button type="button" variant="secondary" disabled={attrs.length===1} onClick={()=>setAttrs(rows=>rows.filter((_,j)=>j!==i))}>×</Button></div>)}<Button type="button" variant="secondary" onClick={()=>setAttrs(rows=>[...rows,{key:'',value:'',type:'string'}])}>Agregar atributo</Button></section>}
      {product&&!variant&&<div><Label>Variante *</Label><Select value={form.producto_variante_id||(variants.length===1?String(variants[0].variante_id):'')} onValueChange={v=>setForm(f=>({...f,producto_variante_id:v}))}><SelectTrigger><SelectValue placeholder="Seleccionar variante…"/></SelectTrigger><SelectContent>{variants.map(v=><SelectItem key={v.variante_id} value={String(v.variante_id)}>{Object.entries(v.atributos||{}).map(([k,value])=>k+': '+value).join(' · ')||'Predeterminada'}</SelectItem>)}</SelectContent></Select>{!variants.length&&<p className="text-xs">No hay variantes activas disponibles. Puedes proponer una nueva variante.</p>}</div>}
      <div className="grid grid-cols-2 gap-3"><div><Label>Tu precio (GTQ) *</Label><Input required type="number" min="0.01" step="0.01" value={form.precio} onChange={e=>setForm(f=>({...f,precio:e.target.value}))}/></div><div><Label>Stock inicial *</Label><Input required type="number" min="0" step="1" value={form.stock} onChange={e=>setForm(f=>({...f,stock:e.target.value}))}/></div></div>
      <Label>Observaciones</Label><Input value={form.observaciones} onChange={e=>setForm(f=>({...f,observaciones:e.target.value}))}/><p className="text-xs">Los SKU se generan automáticamente al aprobar.</p><div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={()=>onOpenChange(false)}>Cancelar</Button><Button loading={mutation.isPending} type="submit">Enviar solicitud</Button></div>
    </form></DialogContent></Dialog>
}

// Sección del vendedor: accesos a proponer producto u oferta, y lista de sus solicitudes enviadas con opción de cancelar las pendientes
export function CatalogRequestsSection() {
  const queryClient = useQueryClient()
  const [productOpen, setProductOpen] = useState(false)
  const [offerOpen, setOfferOpen] = useState(false)
  const [variantOpen, setVariantOpen] = useState(false)
  const [page, setPage] = useState(1)
  const { data, isLoading, isError } = useQuery({ queryKey: ['vendor-catalog-requests',page], queryFn: () => getCatalogRequests(page).then(r => r.data) })
  const cancelMutation = useMutation({ mutationFn: cancelCatalogRequest, onSuccess: () => { toast.success('Solicitud cancelada.'); queryClient.invalidateQueries({ queryKey: ['vendor-catalog-requests'] }) }, onError: err => toast.error(err?.response?.data?.detail || 'No se pudo cancelar.') })
  const rows = data?.items || []
  return <div className="space-y-4">
    {isError && <p role="alert">No se pudieron cargar las solicitudes. Intenta nuevamente.</p>}
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3"><button onClick={() => setProductOpen(true)} className="text-left p-4 border border-[var(--color-border)] rounded-[var(--radius-lg)] bg-[var(--color-surface)] hover:border-[var(--color-action)]"><FilePlus2 className="text-[var(--color-action)] mb-2" /><p className="font-display font-semibold">Proponer producto</p><p className="text-xs text-[var(--color-text-muted)]">Información, categorías, imágenes y oferta inicial.</p></button><button onClick={() => setVariantOpen(true)} className="text-left p-4 border border-[var(--color-border)] rounded-[var(--radius-lg)] bg-[var(--color-surface)] hover:border-[var(--color-action)]"><Sparkles className="text-[var(--color-action)] mb-2" /><p className="font-display font-semibold">Proponer variante</p><p className="text-xs text-[var(--color-text-muted)]">Atributos diferentes, precio y stock inicial.</p></button><button onClick={() => setOfferOpen(true)} className="text-left p-4 border border-[var(--color-border)] rounded-[var(--radius-lg)] bg-[var(--color-surface)] hover:border-[var(--color-jade)]"><Layers className="text-[var(--color-jade)] mb-2" /><p className="font-display font-semibold">Solicitar oferta</p><p className="text-xs text-[var(--color-text-muted)]">Tu precio y stock para un producto ya publicado.</p></button></div>
    <div className="space-y-2">{isLoading ? <Skeleton className="h-24" /> : rows.length === 0 ? <div className="py-12 text-center text-sm text-[var(--color-text-muted)]">Todavía no has enviado solicitudes.</div> : rows.map(row => <div key={row.id} className="p-4 border border-[var(--color-border)] rounded-[var(--radius-lg)] bg-[var(--color-surface)] flex gap-4 items-start"><div className="flex-1"><div className="flex items-center gap-2"><span className="font-mono text-xs">#{row.id}</span><Badge variant={STATUS[row.estado]}>{row.estado}</Badge><Badge variant="secondary">{requestType(row.tipo)}</Badge></div><p className="font-display font-semibold mt-2"><Link to={'/vendor/requests/'+row.id} className="text-[var(--color-action)]">{row.nombre || row.producto_nombre} →</Link></p><p className="text-xs text-[var(--color-text-muted)] mt-1">{formatQ(row.precio_propuesto)} · {row.stock_propuesto} unidades · {formatDate(row.fecha_creacion)}</p>{row.observaciones_admin && <p className="text-xs mt-2 p-2 rounded bg-[var(--color-background)]">Administrador: {row.observaciones_admin}</p>}</div>{row.estado === 'pendiente' && <Button size="sm" variant="secondary" onClick={() => cancelMutation.mutate(row.id)}>Cancelar</Button>}</div>)}</div>
    <ProductProposalDialog open={productOpen} onOpenChange={setProductOpen} />
    <div className="flex gap-3"><Button variant="secondary" disabled={page===1} onClick={()=>setPage(p=>p-1)}>Anterior</Button><span>{page} / {data?.total_pages||1}</span><Button variant="secondary" disabled={page>=(data?.total_pages||1)} onClick={()=>setPage(p=>p+1)}>Siguiente</Button></div>
    <OfferProposalDialog open={variantOpen} onOpenChange={setVariantOpen} variant />
    <OfferProposalDialog open={offerOpen} onOpenChange={setOfferOpen} />
  </div>
}
