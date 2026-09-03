import {useState} from 'react'
import {Link,useParams,useNavigate} from 'react-router-dom'
import {useQuery,useMutation,useQueryClient} from '@tanstack/react-query'
import {toast} from 'sonner'
import {getAdminCategories,updateCategorySchema,createCategory} from '../api/admin'
import {getAdminProducts} from '../api/products'
import {AttrRow} from './AdminPage'
import {Button} from '../components/ui/button'
import {Input} from '../components/ui/input'
import {Label} from '../components/ui/label'
import {Select,SelectTrigger,SelectValue,SelectContent,SelectItem} from '../components/ui/select'

function NewCategory(){
  const navigate=useNavigate();const cache=useQueryClient()
  const [form,setForm]=useState({nombre:'',slug:'',descripcion:'',padre_id:'',sku_prefix:''});const [attrs,setAttrs]=useState([])
  const {data:categories=[]}=useQuery({queryKey:['admin-categories'],queryFn:()=>getAdminCategories().then(r=>r.data)})
  const mutation=useMutation({mutationFn:()=>createCategory({...form,padre_id:form.padre_id?Number(form.padre_id):null,sku_prefix:form.sku_prefix||undefined,atributos:attrs}),onSuccess:()=>{cache.invalidateQueries({queryKey:['admin-categories']});cache.invalidateQueries({queryKey:['categories']});toast.success('Categoría creada.');navigate('/admin/categories/'+form.slug)},onError:e=>{const d=e.response?.data?.detail;toast.error(typeof d==='string'?d:d?.message||'No se pudo crear la categoría.')}})
  return <main className="max-w-5xl mx-auto p-6 space-y-5"><Link to="/admin?section=categories">← Categorías</Link><h1 className="text-2xl font-bold">Nueva categoría</h1><form className="space-y-4 border rounded-xl p-5" onSubmit={e=>{e.preventDefault();mutation.mutate()}}>{[['nombre','Nombre'],['slug','Slug (identificador de URL)'],['descripcion','Descripción'],['sku_prefix','Prefijo SKU']].map(([key,label])=><div key={key}><Label htmlFor={key}>{label}</Label><Input id={key} required={['nombre','slug'].includes(key)} value={form[key]} onChange={e=>setForm(f=>({...f,[key]:e.target.value}))}/></div>)}<Label>Categoría padre</Label><Select value={form.padre_id||'none'} onValueChange={v=>setForm(f=>({...f,padre_id:v==='none'?'':v}))}><SelectTrigger><SelectValue/></SelectTrigger><SelectContent><SelectItem value="none">Sin categoría padre</SelectItem>{categories.map(c=><SelectItem key={c.id} value={String(c.id)}>{c.nombre}</SelectItem>)}</SelectContent></Select><h2 className="font-semibold">Atributos de los productos</h2>{attrs.map((a,i)=><AttrRow key={i} attr={a} onChange={v=>setAttrs(rows=>rows.map((r,j)=>j===i?v:r))} onRemove={()=>setAttrs(rows=>rows.filter((_,j)=>j!==i))}/>)}<div className="flex gap-3"><Button type="button" variant="secondary" onClick={()=>setAttrs(rows=>[...rows,{nombre:'',etiqueta:'',tipo:'string',requerido:false,placeholder:''}])}>Agregar campo</Button><Button type="submit" loading={mutation.isPending}>Crear categoría</Button></div></form></main>
}

function CategoryForm({category}){
  const [attrs,setAttrs]=useState(category.atributos||[]);const [prefix,setPrefix]=useState(category.sku_prefix||'');const cache=useQueryClient()
  const mutation=useMutation({mutationFn:()=>updateCategorySchema(category.slug,{atributos:attrs,sku_prefix:prefix,categoria_nombre:category.nombre}),onSuccess:()=>{toast.success('Campos actualizados.');cache.invalidateQueries({queryKey:['admin-categories']});cache.invalidateQueries({queryKey:['category-schema']})},onError:e=>toast.error(e.response?.data?.detail||'No se pudieron guardar los campos.')})
  return <form className="border rounded-xl p-5 space-y-4" onSubmit={e=>{e.preventDefault();mutation.mutate()}}><h2 className="text-xl font-semibold">Campos de la categoría</h2><div><Label>Prefijo SKU</Label><Input className="max-w-xs" value={prefix} maxLength={3} onChange={e=>setPrefix(e.target.value.toUpperCase())}/></div>{attrs.map((attr,i)=><AttrRow key={i} attr={attr} onChange={value=>setAttrs(rows=>rows.map((r,j)=>j===i?value:r))} onRemove={()=>setAttrs(rows=>rows.filter((_,j)=>j!==i))}/>)}<div className="flex gap-3"><Button type="button" variant="secondary" onClick={()=>setAttrs(rows=>[...rows,{nombre:'',etiqueta:'',tipo:'string',requerido:false,placeholder:''}])}>Agregar campo</Button><Button loading={mutation.isPending} type="submit">Guardar campos</Button></div><p className="text-xs">Cambiar el esquema no rellena ni modifica automáticamente atributos históricos de productos existentes.</p></form>
}

function ExistingCategory(){
  const {slug}=useParams();const [page,setPage]=useState(1)
  const {data:categories=[],isLoading}=useQuery({queryKey:['admin-categories'],queryFn:()=>getAdminCategories().then(r=>r.data)})
  const {data:products,isError}=useQuery({queryKey:['category-products',slug,page],queryFn:()=>getAdminProducts({categoria:slug,estado:'todos',page,page_size:20}).then(r=>r.data)})
  const category=categories.find(c=>c.slug===slug)
  return <main className="max-w-6xl mx-auto p-6 space-y-5"><Link to="/admin?section=categories">← Categorías</Link>{isLoading?<p>Cargando…</p>:!category?<p>Categoría no encontrada.</p>:<><h1 className="text-2xl font-bold">{category.nombre}</h1><p>{category.descripcion} · {category.activa?'Activa':'Inactiva'} · {category.slug}</p><p>Categoría padre: {categories.find(c=>c.id===category.padre_id)?.nombre||'Sin categoría padre'}</p><CategoryForm key={category.id} category={category}/><section className="space-y-3"><h2 className="text-xl font-semibold">Productos asociados ({products?.total||0})</h2>{isError?<p role="alert">No se pudieron consultar los productos.</p>:products?.items.map(p=><Link key={p._id} to={`/admin/products/${p._id}`} className="block border rounded p-3">{p.nombre} · {p.sku} · {p.estado}</Link>)}<div className="flex gap-3"><Button variant="secondary" disabled={page===1} onClick={()=>setPage(p=>p-1)}>Anterior</Button><span>{page} / {products?.total_pages||1}</span><Button variant="secondary" disabled={page>=(products?.total_pages||1)} onClick={()=>setPage(p=>p+1)}>Siguiente</Button></div></section></>}</main>
}

export default function AdminCategoryPage(){const {slug}=useParams();return slug==='new'?<NewCategory/>:<ExistingCategory/>}
