import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Link, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { register } from '../api/auth'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'

const schema = z
  .object({
    nombre: z.string().min(1, 'El nombre es requerido'),
    apellido: z.string().min(1, 'El apellido es requerido'),
    email: z.string().email('Ingresa un correo electrónico válido'),
    password: z.string().min(6, 'La contraseña debe tener al menos 6 caracteres'),
    confirmPassword: z.string().min(1, 'Confirma tu contraseña'),
  })
  .refine((d) => d.password === d.confirmPassword, {
    message: 'Las contraseñas no coinciden',
    path: ['confirmPassword'],
  })

export default function RegisterPage() {
  const navigate = useNavigate()

  const {
    register: reg,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm({ resolver: zodResolver(schema) })

  async function onSubmit(values) {
    try {
      await register({
        nombre: values.nombre,
        apellido: values.apellido,
        email: values.email,
        password: values.password,
      })
      toast.success('Cuenta creada exitosamente. Inicia sesión.')
      navigate('/login')
    } catch (err) {
      const msg =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        'No se pudo crear la cuenta. Intenta de nuevo.'
      setError('root', { message: msg })
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-background)] px-4 py-12">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="font-display font-bold text-3xl text-[var(--color-text-primary)] mb-2">
            Crear cuenta
          </h1>
          <p className="font-sans text-sm text-[var(--color-text-secondary)]">
            Únete a TiendaYa y empieza a comprar
          </p>
        </div>

        <div className="bg-[var(--color-surface)] rounded-[var(--radius-xl)] border border-[var(--color-border)] shadow-[var(--shadow-md)] p-8">
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="nombre">Nombre</Label>
                <Input
                  id="nombre"
                  placeholder="Juan"
                  error={!!errors.nombre}
                  {...reg('nombre')}
                />
                {errors.nombre && (
                  <p className="mt-1 text-xs font-sans text-[var(--color-error)]">
                    {errors.nombre.message}
                  </p>
                )}
              </div>
              <div>
                <Label htmlFor="apellido">Apellido</Label>
                <Input
                  id="apellido"
                  placeholder="García"
                  error={!!errors.apellido}
                  {...reg('apellido')}
                />
                {errors.apellido && (
                  <p className="mt-1 text-xs font-sans text-[var(--color-error)]">
                    {errors.apellido.message}
                  </p>
                )}
              </div>
            </div>

            <div>
              <Label htmlFor="email">Correo electrónico</Label>
              <Input
                id="email"
                type="email"
                placeholder="tu@correo.com"
                error={!!errors.email}
                {...reg('email')}
              />
              {errors.email && (
                <p className="mt-1 text-xs font-sans text-[var(--color-error)]">
                  {errors.email.message}
                </p>
              )}
            </div>

            <div>
              <Label htmlFor="password">Contraseña</Label>
              <Input
                id="password"
                type="password"
                placeholder="Mínimo 6 caracteres"
                error={!!errors.password}
                {...reg('password')}
              />
              {errors.password && (
                <p className="mt-1 text-xs font-sans text-[var(--color-error)]">
                  {errors.password.message}
                </p>
              )}
            </div>

            <div>
              <Label htmlFor="confirmPassword">Confirmar contraseña</Label>
              <Input
                id="confirmPassword"
                type="password"
                placeholder="Repite tu contraseña"
                error={!!errors.confirmPassword}
                {...reg('confirmPassword')}
              />
              {errors.confirmPassword && (
                <p className="mt-1 text-xs font-sans text-[var(--color-error)]">
                  {errors.confirmPassword.message}
                </p>
              )}
            </div>

            {errors.root && (
              <div className="rounded-[var(--radius-md)] bg-[var(--color-error)]/10 border border-[var(--color-error)]/30 px-4 py-3">
                <p className="text-sm font-sans text-[var(--color-error)]">
                  {errors.root.message}
                </p>
              </div>
            )}

            <Button type="submit" size="lg" className="w-full" loading={isSubmitting}>
              Crear cuenta
            </Button>
          </form>

          <p className="mt-6 text-center font-sans text-sm text-[var(--color-text-secondary)]">
            ¿Ya tienes cuenta?{' '}
            <Link to="/login" className="text-[var(--color-action)] font-semibold hover:underline">
              Iniciar sesión
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
