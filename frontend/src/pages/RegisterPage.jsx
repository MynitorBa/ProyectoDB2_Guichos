import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Link, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { CheckCircle2, XCircle } from 'lucide-react'
import { register, login, me } from '../api/auth'
import { createAddress } from '../api/orders'
import { useAuth } from '../context/AuthContext'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'

const PASSWORD_RULES = [
  { id: 'len',     label: 'Mínimo 8 caracteres',          test: (v) => v.length >= 8 },
  { id: 'upper',   label: 'Al menos una mayúscula (A-Z)', test: (v) => /[A-Z]/.test(v) },
  { id: 'lower',   label: 'Al menos una minúscula (a-z)', test: (v) => /[a-z]/.test(v) },
  { id: 'digit',   label: 'Al menos un número (0-9)',     test: (v) => /\d/.test(v) },
  { id: 'special', label: 'Al menos un carácter especial (!@#$%...)', test: (v) => /[^A-Za-z0-9]/.test(v) },
]

const schema = z
  .object({
    nombre: z.string().min(1, 'El nombre es requerido'),
    apellido: z.string().min(1, 'El apellido es requerido'),
    email: z.string().email('Ingresa un correo electrónico válido'),
    password: z
      .string()
      .min(8, 'Mínimo 8 caracteres')
      .regex(/[A-Z]/, 'Debe incluir al menos una mayúscula')
      .regex(/[a-z]/, 'Debe incluir al menos una minúscula')
      .regex(/\d/, 'Debe incluir al menos un número')
      .regex(/[^A-Za-z0-9]/, 'Debe incluir al menos un carácter especial'),
    confirmPassword: z.string().min(1, 'Confirma tu contraseña'),
    departamento: z.string().min(1, 'El departamento es requerido'),
    municipio: z.string().min(1, 'El municipio es requerido'),
    linea1: z.string().min(1, 'La dirección es requerida'),
    linea2: z.string().optional(),
  })
  .refine((d) => d.password === d.confirmPassword, {
    message: 'Las contraseñas no coinciden',
    path: ['confirmPassword'],
  })

function PasswordStrength({ value }) {
  if (!value) return null
  return (
    <ul className="mt-2 space-y-1">
      {PASSWORD_RULES.map((rule) => {
        const ok = rule.test(value)
        return (
          <li key={rule.id} className="flex items-center gap-1.5">
            {ok
              ? <CheckCircle2 size={13} className="text-[var(--color-success,#16a34a)] shrink-0" />
              : <XCircle     size={13} className="text-[var(--color-text-muted)] shrink-0" />
            }
            <span className={`font-sans text-xs ${ok ? 'text-[var(--color-success,#16a34a)]' : 'text-[var(--color-text-muted)]'}`}>
              {rule.label}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

function FieldError({ error }) {
  if (!error) return null
  return <p className="mt-1 text-xs font-sans text-[var(--color-error)]">{error.message}</p>
}

export default function RegisterPage() {
  const navigate = useNavigate()
  const { signIn } = useAuth()

  const {
    register: reg,
    handleSubmit,
    setError,
    watch,
    formState: { errors, isSubmitting },
  } = useForm({ resolver: zodResolver(schema) })

  const passwordValue = watch('password', '')

  async function onSubmit(values) {
    try {
      // 1. Crear cuenta
      await register({
        nombre: values.nombre,
        apellido: values.apellido,
        email: values.email,
        password: values.password,
      })

      // 2. Auto-login para obtener token
      const loginRes = await login(values.email, values.password)
      const { access_token } = loginRes.data
      localStorage.setItem('token', access_token)

      // 3. Guardar la dirección con el token activo
      await createAddress({
        tipo: 'envio',
        pais: 'Guatemala',
        departamento: values.departamento,
        municipio: values.municipio,
        linea1: values.linea1,
        linea2: values.linea2 || null,
        codigo_postal: null,
        es_predeterminada: false,
      })

      // 4. Cargar datos del usuario y establecer sesión
      const userData = await me().then((r) => r.data)
      signIn(access_token, userData)

      toast.success('Cuenta creada exitosamente. ¡Bienvenido!')
      navigate('/')
    } catch (err) {
      localStorage.removeItem('token')
      const msg =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        'No se pudo crear la cuenta. Intenta de nuevo.'
      setError('root', { message: msg })
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-background)] px-4 py-12">
      <div className="w-full max-w-lg">
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

            {/* Datos personales */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="nombre">Nombre</Label>
                <Input id="nombre" placeholder="Juan" error={!!errors.nombre} {...reg('nombre')} />
                <FieldError error={errors.nombre} />
              </div>
              <div>
                <Label htmlFor="apellido">Apellido</Label>
                <Input id="apellido" placeholder="García" error={!!errors.apellido} {...reg('apellido')} />
                <FieldError error={errors.apellido} />
              </div>
            </div>

            <div>
              <Label htmlFor="email">Correo electrónico</Label>
              <Input id="email" type="email" placeholder="tu@correo.com" error={!!errors.email} {...reg('email')} />
              <FieldError error={errors.email} />
            </div>

            <div>
              <Label htmlFor="password">Contraseña</Label>
              <Input id="password" type="password" placeholder="Mínimo 8 caracteres" error={!!errors.password} {...reg('password')} />
              <PasswordStrength value={passwordValue} />
              <FieldError error={errors.password} />
            </div>

            <div>
              <Label htmlFor="confirmPassword">Confirmar contraseña</Label>
              <Input id="confirmPassword" type="password" placeholder="Repite tu contraseña" error={!!errors.confirmPassword} {...reg('confirmPassword')} />
              <FieldError error={errors.confirmPassword} />
            </div>

            {/* Separador dirección */}
            <div className="pt-2 pb-1">
              <p className="font-display font-semibold text-sm text-[var(--color-text-primary)]">
                Dirección de envío
              </p>
              <p className="font-sans text-xs text-[var(--color-text-muted)] mt-0.5">
                Podrás agregar más direcciones desde tu perfil.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="departamento">Departamento</Label>
                <Input id="departamento" placeholder="Guatemala" error={!!errors.departamento} {...reg('departamento')} />
                <FieldError error={errors.departamento} />
              </div>
              <div>
                <Label htmlFor="municipio">Municipio</Label>
                <Input id="municipio" placeholder="Guatemala" error={!!errors.municipio} {...reg('municipio')} />
                <FieldError error={errors.municipio} />
              </div>
            </div>

            <div>
              <Label htmlFor="linea1">Dirección</Label>
              <Input id="linea1" placeholder="Calle, número, colonia..." error={!!errors.linea1} {...reg('linea1')} />
              <FieldError error={errors.linea1} />
            </div>

            <div>
              <Label htmlFor="linea2">Dirección línea 2 (opcional)</Label>
              <Input id="linea2" placeholder="Apartamento, edificio..." {...reg('linea2')} />
            </div>

            {errors.root && (
              <div className="rounded-[var(--radius-md)] bg-[var(--color-error)]/10 border border-[var(--color-error)]/30 px-4 py-3">
                <p className="text-sm font-sans text-[var(--color-error)]">{errors.root.message}</p>
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
