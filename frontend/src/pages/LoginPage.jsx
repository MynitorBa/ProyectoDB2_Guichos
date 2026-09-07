import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Link, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { login, me } from '../api/auth'
import { useAuth } from '../context/AuthContext'
import { motion } from 'motion/react'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'

const ease = [0.23, 1, 0.32, 1]

const schema = z.object({
  email: z.string().email('Ingresa un correo electrónico válido'),
  password: z.string().min(1, 'La contraseña es requerida'),
})

// Página de login: valida con Zod, llama a /auth/login y luego a /auth/me para obtener los datos del usuario
export default function LoginPage() {
  const navigate = useNavigate()
  const { signIn } = useAuth()

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm({ resolver: zodResolver(schema) })

  async function onSubmit(values) {
    try {
      const res = await login(values.email, values.password)
      const { access_token } = res.data
      // Guardar token antes de llamar me() para que el interceptor lo incluya
      localStorage.setItem('token', access_token)
      const userData = await me().then((r) => r.data)
      signIn(access_token, userData)
      toast.success('Bienvenido de vuelta')
      navigate('/')
    } catch (err) {
      localStorage.removeItem('token')
      const msg =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        'Credenciales incorrectas. Intenta de nuevo.'
      setError('root', { message: msg })
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-background)] px-4 py-12">
      <motion.div
        className="w-full max-w-md"
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease }}
      >
        <motion.div
          className="text-center mb-8"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease, delay: 0.08 }}
        >
          <h1 className="font-display font-bold text-3xl text-[var(--color-text-primary)] mb-2">
            Iniciar sesión
          </h1>
          <p className="font-sans text-sm text-[var(--color-text-secondary)]">
            Accede a tu cuenta de TiendaYa
          </p>
        </motion.div>

        <motion.div
          className="bg-[var(--color-surface)] rounded-[var(--radius-xl)] border border-[var(--color-border)] shadow-[var(--shadow-md)] p-8"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, ease, delay: 0.15 }}
        >
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-5" noValidate>
            <div>
              <Label htmlFor="email">Correo electrónico</Label>
              <Input
                id="email"
                type="email"
                placeholder="tu@correo.com"
                error={!!errors.email}
                {...register('email')}
              />
              {errors.email && (
                <p className="mt-1.5 text-xs font-sans text-[var(--color-error)]">
                  {errors.email.message}
                </p>
              )}
            </div>

            <div>
              <Label htmlFor="password">Contraseña</Label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                error={!!errors.password}
                {...register('password')}
              />
              {errors.password && (
                <p className="mt-1.5 text-xs font-sans text-[var(--color-error)]">
                  {errors.password.message}
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
              Entrar
            </Button>
          </form>

          <p className="mt-6 text-center font-sans text-sm text-[var(--color-text-secondary)]">
            ¿No tienes cuenta?{' '}
            <Link to="/register" className="text-[var(--color-action)] font-semibold hover:underline">
              Crear cuenta gratis
            </Link>
          </p>
        </motion.div>
      </motion.div>
    </div>
  )
}
