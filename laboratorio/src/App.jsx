import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FlaskConical, LogOut, ExternalLink, ShieldAlert } from 'lucide-react'

import { API_URL, TIENDA_URL, cerrarSesion, iniciarSesion, obtenerToken, api } from './api'
import { Boton } from './ui'
import {
  PanelBitacora, PanelCasos, PanelComponentes, PanelInvariantes, PanelOutbox, PanelPasarela,
  PanelPuntosFalla, PanelRecuperacion,
} from './paneles'

function Cabecera({ onSalir }) {
  return (
    <header className="bg-[var(--color-lab)] text-white">
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <FlaskConical size={22} className="text-amber-300" />
          <div>
            <h1 className="font-semibold text-lg leading-tight">Laboratorio de consistencia</h1>
            <p className="text-xs text-gray-400">Herramienta de desarrollo para provocar fallas en TiendaYa y observar su recuperación · no forma parte de la tienda</p>
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <a href={TIENDA_URL} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-gray-300 hover:text-white">
            Abrir la tienda <ExternalLink size={12} />
          </a>
          {onSalir && (
            <button type="button" onClick={onSalir} className="flex items-center gap-1 text-gray-300 hover:text-white">
              <LogOut size={13} /> Salir
            </button>
          )}
        </div>
      </div>
    </header>
  )
}

function Ingreso({ onIngreso }) {
  const [email, setEmail] = useState('admin@tiendaya.gt')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  async function enviar(e) {
    e.preventDefault()
    setError('')
    setEnviando(true)
    try {
      await iniciarSesion(email, password)
      onIngreso()
    } catch (err) {
      setError(err.status === 401 ? 'Credenciales incorrectas.' : err.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="min-h-screen">
      <Cabecera />
      <form onSubmit={enviar} className="max-w-sm mx-auto mt-16 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl p-6 space-y-4">
        <div>
          <h2 className="font-semibold">Ingresa como administrador de TiendaYa</h2>
          <p className="text-xs text-[var(--color-text-muted)] mt-1">El laboratorio usa la API del backend ({API_URL}).</p>
        </div>
        <label className="block text-sm">
          Correo
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full h-9 px-3 rounded-md border border-[var(--color-border)] text-sm" />
        </label>
        <label className="block text-sm">
          Contraseña
          <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full h-9 px-3 rounded-md border border-[var(--color-border)] text-sm" />
        </label>
        {error && <p role="alert" className="text-sm text-[var(--color-error)]">{error}</p>}
        <Boton type="submit" cargando={enviando} className="w-full h-9">Entrar</Boton>
      </form>
    </div>
  )
}

function SinAcceso({ error, onSalir }) {
  const deshabilitado = error.status === 404
  return (
    <div className="min-h-screen">
      <Cabecera onSalir={onSalir} />
      <div className="max-w-xl mx-auto mt-16 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl p-6 space-y-3">
        <p className="flex items-center gap-2 font-semibold"><ShieldAlert size={18} className="text-[var(--color-warning)]" />
          {deshabilitado ? 'La inyección de fallas está deshabilitada en el backend' : 'No se puede usar el laboratorio'}</p>
        {deshabilitado ? (
          <p className="text-sm text-[var(--color-text-secondary)]">
            El backend solo registra los endpoints de fallas en desarrollo. Agrega <code className="font-mono bg-[var(--color-background)] px-1 rounded">FAULT_INJECTION_ENABLED=true</code> a{' '}
            <code className="font-mono bg-[var(--color-background)] px-1 rounded">backend/.env</code> y reinicia el backend.
          </p>
        ) : (
          <p className="text-sm text-[var(--color-text-secondary)]">
            {error.status === 403 ? 'Esta cuenta no es de administrador.' : error.message}
          </p>
        )}
      </div>
    </div>
  )
}

export default function App() {
  const queryClient = useQueryClient()
  const [sesion, setSesion] = useState(Boolean(obtenerToken()))
  const fallas = useQuery({
    queryKey: ['fallas'],
    queryFn: api.fallas,
    enabled: sesion,
    refetchInterval: 3000,
    retry: false,
  })

  function salir() {
    cerrarSesion()
    queryClient.clear()
    setSesion(false)
  }

  if (!sesion || fallas.error?.status === 401) {
    return <Ingreso onIngreso={() => { setSesion(true); queryClient.invalidateQueries() }} />
  }
  if (fallas.error) {
    return <SinAcceso error={fallas.error} onSalir={salir} />
  }

  return (
    <div className="min-h-screen">
      <Cabecera onSalir={salir} />
      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {fallas.data && !fallas.data.habilitada && (
          <p role="status" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
            Modo seguro: la inyección de fallas está deshabilitada. Los diagnósticos siguen disponibles;
            los controles que modifican el entorno están bloqueados.
          </p>
        )}
        <p className="text-sm text-[var(--color-text-secondary)] max-w-3xl">
          Provoca una falla, haz una compra en la tienda y observa aquí cómo responde el checkout distribuido: la saga compensa,
          los reintentos idempotentes evitan cobros dobles, el outbox retiene y reenvía los eventos, y los invariantes confirman
          que nada quedó inconsistente.
        </p>
        <PanelCasos habilitado={fallas.data?.habilitada} />
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <PanelPasarela estado={fallas.data} habilitado={fallas.data?.habilitada} />
          <PanelPuntosFalla estado={fallas.data} habilitado={fallas.data?.habilitada} />
          <PanelComponentes habilitado={fallas.data?.habilitada} />
        </div>
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <PanelOutbox habilitado={fallas.data?.habilitada} />
          <PanelRecuperacion habilitado={fallas.data?.habilitada} />
          <PanelInvariantes />
        </div>
        <PanelBitacora />
      </main>
    </div>
  )
}
