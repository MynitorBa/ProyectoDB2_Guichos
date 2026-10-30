// Productos vistos en este navegador, para «Te podría interesar» sin sesión.
// Con sesión, el historial también se guarda en el servidor (Redis).
const CLAVE = 'tiendaya:vistos'
const MAX_VISTOS = 10

export function leerVistos() {
  try {
    const vistos = JSON.parse(localStorage.getItem(CLAVE) || '[]')
    return Array.isArray(vistos) ? vistos.slice(0, MAX_VISTOS) : []
  } catch {
    return []
  }
}

export function agregarVisto(id) {
  if (!id) return
  try {
    const vistos = [id, ...leerVistos().filter((v) => v !== id)].slice(0, MAX_VISTOS)
    localStorage.setItem(CLAVE, JSON.stringify(vistos))
  } catch {
    // Sin almacenamiento local (modo privado): solo se pierde la personalización.
  }
}
