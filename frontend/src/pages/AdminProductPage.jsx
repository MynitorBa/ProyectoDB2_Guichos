import {useState} from 'react'
import {Link,useNavigate,useParams,useSearchParams} from 'react-router-dom'
import {useQuery} from '@tanstack/react-query'
import {getProduct} from '../api/products'
import {ProductFormModal,VariantsModal,OffersModal} from './AdminPage'
import {RecordMode} from '../components/ui/record-dialog'
import {Button} from '../components/ui/button'

export default function AdminProductPage(){
  const {id}=useParams(); const navigate=useNavigate();const [params]=useSearchParams()
  const [tab,setTab]=useState(params.get('tab')||'general');const fresh=id==='new'
  const {data:product,isLoading,isError}=useQuery({queryKey:['admin-product-record',id],queryFn:()=>getProduct(id).then(r=>r.data),enabled:!fresh})
  const back=()=>navigate('/admin?section=products')
  return <main className="max-w-6xl mx-auto p-6 space-y-5"><Link to="/admin?section=products">← Productos</Link>
    {!fresh&&isLoading?<p>Cargando ficha…</p>:!fresh&&(isError||!product)?<p role="alert">No se pudo cargar el producto.</p>:<>
      <header><h1 className="text-2xl font-bold">{fresh?'Nuevo producto':product.nombre}</h1>{!fresh&&<p className="font-mono text-sm">{product.sku} · {product.estado}</p>}</header>
      {!fresh&&<nav className="flex flex-wrap gap-2">{[['general','Datos e imágenes'],['variants','Variantes'],['offers','Ofertas por vendedor']].map(([key,label])=><Button key={key} variant={tab===key?'primary':'secondary'} onClick={()=>setTab(key)}>{label}</Button>)}<Link className="p-2 text-[var(--color-action)]" to={`/admin/products/${id}/history`}>Historial</Link></nav>}
      <RecordMode.Provider value={true}>{(fresh||tab==='general')&&<ProductFormModal open onOpenChange={back} product={product} onDuplicateFound={p=>navigate(`/admin/products/${p._id}`)}/>}{!fresh&&tab==='variants'&&<VariantsModal open onOpenChange={()=>setTab('general')} product={product}/>} {!fresh&&tab==='offers'&&<OffersModal open onOpenChange={()=>setTab('general')} product={product}/>}</RecordMode.Provider>
    </>}
  </main>
}
