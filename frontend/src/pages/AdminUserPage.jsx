import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ShieldCheck, ShoppingBag, User, ExternalLink } from 'lucide-react'
import api from '../api/client'
import { updateUserRoles, setVendorProfile } from '../api/admin'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Badge } from '../components/ui/badge'

const ROLE_META = {
  administrador: {
    label: 'Admin',
    Icon: ShieldCheck,
    active: 'bg-[var(--color-action)] text-white border-[var(--color-action)]',
    inactive: 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-action)] hover:text-[var(--color-action)]',
  },
  vendedor: {
    label: 'Vendedor',
    Icon: ShoppingBag,
    active: 'bg-[var(--color-jade)] text-white border-[var(--color-jade)]',
    inactive: 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-jade)] hover:text-[var(--color-jade)]',
  },
  comprador: {
    label: 'Comprador',
    Icon: User,
    active: 'bg-[var(--color-border-strong)] text-[var(--color-text-primary)] border-[var(--color-border-strong)]',
    inactive: 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-border-strong)] hover:text-[var(--color-text-primary)]',
  },
}

export default function AdminUserPage() {
  const { id } = useParams()
  const [name, setName] = useState('')
  const [nit, setNit] = useState('')
  const cache = useQueryClient()
  const { data: u, isLoading, isError } = useQuery({
    queryKey: ['admin-user', id],
    queryFn: () => api.get(`/admin/users/${id}`).then(r => r.data),
  })
  const done = () => {
    cache.invalidateQueries({ queryKey: ['admin-user'] })
    cache.invalidateQueries({ queryKey: ['admin-users'] })
    cache.invalidateQueries({ queryKey: ['admin-vendors'] })
  }
  const roles = useMutation({
    mutationFn: values => updateUserRoles(id, values),
    onSuccess: done,
    onError: e => toast.error(e.response?.data?.detail || 'No se pudieron actualizar los roles.'),
  })
  const profile = useMutation({
    mutationFn: () => setVendorProfile(id, { nombre_comercial: name, nit }),
    onSuccess: done,
    onError: e => toast.error(e.response?.data?.detail || 'No se pudo guardar.'),
  })

  return (
    <main className="max-w-4xl mx-auto p-6 space-y-6">
      <Link to="/admin?section=users" className="text-sm text-[var(--color-action)] hover:underline">← Usuarios</Link>

      {isLoading ? (
        <p className="text-[var(--color-text-secondary)]">Cargando…</p>
      ) : isError ? (
        <p className="text-[var(--color-error)]">Usuario no encontrado.</p>
      ) : (
        <>
          <header>
            <h1 className="text-2xl font-bold font-display">{u.nombre} {u.apellido}</h1>
            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
              <span className="text-sm text-[var(--color-text-secondary)]">{u.email}</span>
              <Badge variant={u.estado === 'activo' ? 'success' : 'default'}>{u.estado}</Badge>
            </div>
          </header>

          <section className="border border-[var(--color-border)] rounded-xl p-6 space-y-5 bg-[var(--color-surface)]">
            <div>
              <h2 className="font-semibold mb-3">Roles del usuario</h2>
              <div className="flex flex-wrap gap-2">
                {['comprador', 'vendedor', 'administrador'].map(role => {
                  const meta = ROLE_META[role]
                  const active = u.roles.includes(role)
                  return (
                    <button
                      key={role}
                      disabled={roles.isPending}
                      onClick={() => roles.mutate(
                        active ? u.roles.filter(r => r !== role) : [...u.roles, role]
                      )}
                      className={[
                        'flex items-center gap-1.5 px-4 py-2 rounded-lg border text-sm font-medium transition-all',
                        active ? meta.active : meta.inactive,
                      ].join(' ')}
                    >
                      <meta.Icon size={14} />
                      {meta.label}
                    </button>
                  )
                })}
              </div>
            </div>
            <p className="text-xs text-[var(--color-text-muted)] bg-[var(--color-background)] rounded-lg px-3 py-2.5">
              Las contraseñas no se muestran ni se recuperan desde esta ficha.
            </p>
          </section>

          {u.vendedor_id ? (
            <Link
              to={`/admin/vendors/${u.vendedor_id}`}
              className="flex items-center gap-2 text-[var(--color-action)] hover:underline font-medium"
            >
              <ExternalLink size={14} />
              Abrir ficha comercial del vendedor
            </Link>
          ) : u.roles.includes('vendedor') && (
            <form
              className="border border-[var(--color-border)] rounded-xl p-6 space-y-4 bg-[var(--color-surface)]"
              onSubmit={e => { e.preventDefault(); profile.mutate() }}
            >
              <h2 className="font-semibold">Crear perfil comercial</h2>
              <div className="grid sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label>Nombre comercial</Label>
                  <Input required value={name} onChange={e => setName(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label>NIT</Label>
                  <Input required value={nit} onChange={e => setNit(e.target.value)} />
                </div>
              </div>
              <Button loading={profile.isPending} type="submit">Crear perfil</Button>
            </form>
          )}
        </>
      )}
    </main>
  )
}
