import { useState, useEffect } from 'react'
import { toast } from 'sonner'
import { Plus, Pencil, Trash2, MapPin, User } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { updateProfile } from '../api/auth'
import { getAddresses, createAddress, updateAddress, deleteAddress } from '../api/orders'
import { Button } from '../components/ui/button'
import {
  Dialog, DialogContent, DialogTitle, DialogDescription, DialogClose,
} from '../components/ui/dialog'
import { cn } from '../lib/utils'

const TIPO_LABELS = { envio: 'Envío', facturacion: 'Facturación' }

const EMPTY_ADDRESS = {
  tipo: 'envio',
  pais: 'Guatemala',
  departamento: '',
  municipio: '',
  linea1: '',
  linea2: '',
  codigo_postal: '',
}

function Field({ label, id, children }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="font-sans text-sm font-medium text-[var(--color-text-secondary)]">
        {label}
      </label>
      {children}
    </div>
  )
}

function Input({ className, ...props }) {
  return (
    <input
      className={cn(
        'h-10 px-3 bg-[var(--color-background)] border border-[var(--color-border)] rounded-[var(--radius-md)]',
        'font-sans text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]',
        'focus:outline-none focus:border-[var(--color-action)] focus:ring-2 focus:ring-[var(--color-action)]/20 transition-colors',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        className,
      )}
      {...props}
    />
  )
}

function AddressDialog({ open, onOpenChange, initial, onSave }) {
  const [form, setForm] = useState(initial || EMPTY_ADDRESS)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setForm(initial || EMPTY_ADDRESS)
  }, [initial, open])

  function set(field, value) {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!form.departamento || !form.municipio || !form.linea1) {
      toast.error('Completa los campos requeridos.')
      return
    }
    setSaving(true)
    try {
      await onSave({
        tipo: form.tipo,
        pais: form.pais || 'Guatemala',
        departamento: form.departamento,
        municipio: form.municipio,
        linea1: form.linea1,
        linea2: form.linea2 || null,
        codigo_postal: form.codigo_postal || null,
        es_predeterminada: false,
      })
      onOpenChange(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>{initial?.id ? 'Editar dirección' : 'Nueva dirección'}</DialogTitle>
        <DialogDescription>
          {initial?.id ? 'Modifica los datos de la dirección.' : 'Agrega una nueva dirección de envío o facturación.'}
        </DialogDescription>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="Tipo" id="tipo">
            <select
              id="tipo"
              value={form.tipo}
              onChange={e => set('tipo', e.target.value)}
              className="h-10 px-3 bg-[var(--color-background)] border border-[var(--color-border)] rounded-[var(--radius-md)] font-sans text-sm text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-action)] focus:ring-2 focus:ring-[var(--color-action)]/20 transition-colors"
            >
              <option value="envio">Envío</option>
              <option value="facturacion">Facturación</option>
            </select>
          </Field>

          <Field label="País" id="pais">
            <Input id="pais" value={form.pais} onChange={e => set('pais', e.target.value)} placeholder="Guatemala" />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Departamento *" id="departamento">
              <Input
                id="departamento"
                value={form.departamento}
                onChange={e => set('departamento', e.target.value)}
                placeholder="Guatemala"
                required
              />
            </Field>
            <Field label="Municipio *" id="municipio">
              <Input
                id="municipio"
                value={form.municipio}
                onChange={e => set('municipio', e.target.value)}
                placeholder="Guatemala"
                required
              />
            </Field>
          </div>

          <Field label="Dirección línea 1 *" id="linea1">
            <Input
              id="linea1"
              value={form.linea1}
              onChange={e => set('linea1', e.target.value)}
              placeholder="Calle, número, colonia..."
              required
            />
          </Field>

          <Field label="Dirección línea 2" id="linea2">
            <Input
              id="linea2"
              value={form.linea2 || ''}
              onChange={e => set('linea2', e.target.value)}
              placeholder="Apartamento, edificio... (opcional)"
            />
          </Field>

          <Field label="Código postal" id="codigo_postal">
            <Input
              id="codigo_postal"
              value={form.codigo_postal || ''}
              onChange={e => set('codigo_postal', e.target.value)}
              placeholder="01001 (opcional)"
            />
          </Field>

          <div className="flex justify-end gap-2 pt-2">
            <DialogClose asChild>
              <Button type="button" variant="ghost">Cancelar</Button>
            </DialogClose>
            <Button type="submit" variant="primary" disabled={saving}>
              {saving ? 'Guardando...' : 'Guardar dirección'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function AddressCard({ address, onEdit, onDelete }) {
  const [deleting, setDeleting] = useState(false)

  async function handleDelete() {
    if (!confirm('¿Eliminar esta dirección?')) return
    setDeleting(true)
    try {
      await onDelete(address.id)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="relative p-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-background)] transition-colors">
      <div className="flex items-start gap-2 mb-2">
        <MapPin size={15} className="text-[var(--color-action)] shrink-0 mt-0.5" />
        <div className="min-w-0">
          <p className="font-display font-semibold text-sm text-[var(--color-text-primary)]">
            {TIPO_LABELS[address.tipo] || address.tipo}
          </p>
          <p className="font-sans text-sm text-[var(--color-text-secondary)] leading-relaxed">
            {address.linea1}
            {address.linea2 && `, ${address.linea2}`}
          </p>
          <p className="font-sans text-sm text-[var(--color-text-secondary)]">
            {address.municipio}, {address.departamento}
            {address.codigo_postal && ` ${address.codigo_postal}`}
          </p>
          <p className="font-sans text-xs text-[var(--color-text-muted)]">{address.pais}</p>
        </div>
      </div>

      <div className="flex justify-end items-center gap-1 mt-3">
        <button
          onClick={() => onEdit(address)}
          className="p-1.5 rounded-[var(--radius-md)] text-[var(--color-text-muted)] hover:bg-[var(--color-border)] hover:text-[var(--color-text-primary)] transition-colors"
        >
          <Pencil size={14} />
        </button>
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="p-1.5 rounded-[var(--radius-md)] text-[var(--color-text-muted)] hover:bg-[var(--color-error-light)] hover:text-[var(--color-error)] transition-colors disabled:opacity-50"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  )
}

export default function ProfilePage() {
  const { user, updateUser } = useAuth()

  const [profileForm, setProfileForm] = useState({
    nombre: user?.nombre || '',
    apellido: user?.apellido || '',
    telefono: user?.telefono || '',
  })
  const [savingProfile, setSavingProfile] = useState(false)

  const [addresses, setAddresses] = useState([])
  const [loadingAddresses, setLoadingAddresses] = useState(true)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingAddress, setEditingAddress] = useState(null)

  useEffect(() => {
    if (user) {
      setProfileForm({
        nombre: user.nombre || '',
        apellido: user.apellido || '',
        telefono: user.telefono || '',
      })
    }
  }, [user])

  useEffect(() => {
    loadAddresses()
  }, [])

  async function loadAddresses() {
    setLoadingAddresses(true)
    try {
      const res = await getAddresses()
      setAddresses(res.data)
    } catch {
      toast.error('Error al cargar las direcciones.')
    } finally {
      setLoadingAddresses(false)
    }
  }

  function setField(field, value) {
    setProfileForm(prev => ({ ...prev, [field]: value }))
  }

  async function handleSaveProfile(e) {
    e.preventDefault()
    if (!profileForm.nombre.trim() || !profileForm.apellido.trim()) {
      toast.error('El nombre y apellido son requeridos.')
      return
    }
    setSavingProfile(true)
    try {
      const res = await updateProfile({
        nombre: profileForm.nombre.trim(),
        apellido: profileForm.apellido.trim(),
        telefono: profileForm.telefono.trim() || null,
      })
      updateUser(res.data)
      toast.success('Perfil actualizado correctamente.')
    } catch {
      toast.error('Error al actualizar el perfil.')
    } finally {
      setSavingProfile(false)
    }
  }

  function openNewAddress() {
    setEditingAddress(null)
    setDialogOpen(true)
  }

  function openEditAddress(address) {
    setEditingAddress(address)
    setDialogOpen(true)
  }

  async function handleSaveAddress(data) {
    try {
      if (editingAddress?.id) {
        const res = await updateAddress(editingAddress.id, data)
        setAddresses(prev => prev.map(a => (a.id === editingAddress.id ? res.data : a)))
        toast.success('Dirección actualizada.')
      } else {
        const res = await createAddress(data)
        setAddresses(prev => [...prev, res.data])
        toast.success('Dirección agregada.')
      }
    } catch {
      toast.error('Error al guardar la dirección.')
      throw new Error('save failed')
    }
  }

  async function handleDeleteAddress(id) {
    try {
      await deleteAddress(id)
      setAddresses(prev => prev.filter(a => a.id !== id))
      toast.success('Dirección eliminada.')
    } catch {
      toast.error('Error al eliminar la dirección.')
    }
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <div className="flex items-center gap-3">
        <div className="h-12 w-12 rounded-full bg-[var(--color-action)]/10 flex items-center justify-center shrink-0">
          <span className="font-display font-bold text-xl text-[var(--color-action)]">
            {user?.nombre?.[0]?.toUpperCase() || 'U'}
          </span>
        </div>
        <div>
          <h1 className="font-display font-bold text-2xl text-[var(--color-text-primary)]">Mi perfil</h1>
          <p className="font-sans text-sm text-[var(--color-text-muted)]">{user?.email}</p>
        </div>
      </div>

      {/* Información personal */}
      <section className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-xl)] p-6">
        <div className="flex items-center gap-2 mb-5">
          <User size={16} className="text-[var(--color-action)]" />
          <h2 className="font-display font-semibold text-base text-[var(--color-text-primary)]">
            Información personal
          </h2>
        </div>

        <form onSubmit={handleSaveProfile} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Nombre *" id="nombre">
              <Input
                id="nombre"
                value={profileForm.nombre}
                onChange={e => setField('nombre', e.target.value)}
                placeholder="Tu nombre"
                required
              />
            </Field>
            <Field label="Apellido *" id="apellido">
              <Input
                id="apellido"
                value={profileForm.apellido}
                onChange={e => setField('apellido', e.target.value)}
                placeholder="Tu apellido"
                required
              />
            </Field>
          </div>

          <Field label="Correo electrónico" id="email">
            <Input id="email" value={user?.email || ''} disabled className="opacity-60" />
          </Field>

          <Field label="Teléfono" id="telefono">
            <Input
              id="telefono"
              value={profileForm.telefono}
              onChange={e => setField('telefono', e.target.value)}
              placeholder="+502 1234-5678 (opcional)"
            />
          </Field>

          <div className="flex justify-end pt-1">
            <Button type="submit" variant="primary" disabled={savingProfile}>
              {savingProfile ? 'Guardando...' : 'Guardar cambios'}
            </Button>
          </div>
        </form>
      </section>

      {/* Mis direcciones */}
      <section className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-xl)] p-6">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2">
            <MapPin size={16} className="text-[var(--color-action)]" />
            <h2 className="font-display font-semibold text-base text-[var(--color-text-primary)]">
              Mis direcciones
            </h2>
          </div>
          <Button variant="primary" size="sm" onClick={openNewAddress}>
            <Plus size={14} className="mr-1" /> Agregar
          </Button>
        </div>

        {loadingAddresses ? (
          <div className="space-y-3">
            {[1, 2].map(i => (
              <div key={i} className="h-24 rounded-[var(--radius-lg)] bg-[var(--color-border)] animate-pulse" />
            ))}
          </div>
        ) : addresses.length === 0 ? (
          <div className="text-center py-10">
            <MapPin size={32} className="mx-auto mb-3 text-[var(--color-text-muted)]" strokeWidth={1} />
            <p className="font-display font-semibold text-sm text-[var(--color-text-secondary)]">
              Sin direcciones guardadas
            </p>
            <p className="font-sans text-xs text-[var(--color-text-muted)] mt-1">
              Agrega una dirección para agilizar tu próxima compra.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {addresses.map(address => (
              <AddressCard
                key={address.id}
                address={address}
                onEdit={openEditAddress}
                onDelete={handleDeleteAddress}
              />
            ))}
          </div>
        )}
      </section>

      <AddressDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        initial={editingAddress}
        onSave={handleSaveAddress}
      />
    </div>
  )
}
