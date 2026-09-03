import {useState} from 'react'
import {Link,useParams} from 'react-router-dom'
import {useQuery,useMutation,useQueryClient} from '@tanstack/react-query'
import {toast} from 'sonner'
import api from '../api/client'
import {updateUserRoles,setVendorProfile} from '../api/admin'
import {Button} from '../components/ui/button'
import {Input} from '../components/ui/input'
import {Label} from '../components/ui/label'

export default function AdminUserPage(){
  const {id}=useParams();const [name,setName]=useState('');const [nit,setNit]=useState('');const cache=useQueryClient()
  const {data:u,isLoading,isError}=useQuery({queryKey:['admin-user',id],queryFn:()=>api.get(`/admin/users/${id}`).then(r=>r.data)})
  const done=()=>{cache.invalidateQueries({queryKey:['admin-user']});cache.invalidateQueries({queryKey:['admin-users']});cache.invalidateQueries({queryKey:['admin-vendors']})}
  const roles=useMutation({mutationFn:values=>updateUserRoles(id,values),onSuccess:done,onError:e=>toast.error(e.response?.data?.detail||'No se pudieron actualizar los roles.')})
  const profile=useMutation({mutationFn:()=>setVendorProfile(id,{nombre_comercial:name,nit}),onSuccess:done,onError:e=>toast.error(e.response?.data?.detail||'No se pudo guardar.')})
  return <main className="max-w-4xl mx-auto p-6 space-y-5"><Link to="/admin?section=users">← Usuarios</Link>{isLoading?<p>Cargando…</p>:isError?<p>Usuario no encontrado.</p>:<><h1 className="text-2xl font-bold">{u.nombre} {u.apellido}</h1><section className="border rounded-xl p-5 space-y-4"><p>Correo de acceso: {u.email}</p><p>Estado: {u.estado}</p><p className="text-sm">Las contraseñas no se muestran ni se recuperan desde esta ficha.</p><h2 className="font-semibold">Roles</h2><div className="flex gap-3">{['comprador','vendedor','administrador'].map(role=><Button key={role} disabled={roles.isPending} variant={u.roles.includes(role)?'primary':'secondary'} onClick={()=>roles.mutate(u.roles.includes(role)?u.roles.filter(r=>r!==role):[...u.roles,role])}>{role}</Button>)}</div></section>{u.vendedor_id?<Link to={`/admin/vendors/${u.vendedor_id}`} className="block text-[var(--color-action)]">Abrir ficha comercial del vendedor →</Link>:u.roles.includes('vendedor')&&<form className="border rounded-lg p-5 space-y-3" onSubmit={e=>{e.preventDefault();profile.mutate()}}><h2 className="font-semibold">Crear perfil comercial</h2><Label>Nombre comercial</Label><Input required value={name} onChange={e=>setName(e.target.value)}/><Label>NIT</Label><Input required value={nit} onChange={e=>setNit(e.target.value)}/><Button loading={profile.isPending} type="submit">Crear perfil</Button></form>}</>}</main>
}
