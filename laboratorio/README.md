# Laboratorio de consistencia

Herramienta de **desarrollo** para provocar fallas en el checkout distribuido de
TiendaYa y observar cómo se recupera. Vive en el mismo repositorio, pero es una
aplicación aparte: no forma parte de la tienda ni de su panel de administración
y se comunica con el backend solo por su API, como cualquier herramienta externa
de pruebas de resiliencia.

| | Tienda | Laboratorio |
|---|---|---|
| Carpeta | `frontend/` | `laboratorio/` |
| Puerto | 5173 | 5174 |
| Público | Clientes, vendedores y administradores | Equipo de desarrollo |
| En producción | Sí | No (el backend ni siquiera registra sus endpoints) |

## Qué permite hacer

- Cambiar el comportamiento de la **pasarela de pagos simulada** (aprobar,
  rechazar, timeout, cobrar y fallar, error 503).
- Activar **puntos de falla** que simulan caídas del backend en un punto exacto
  de la saga (tras reservar, tras cobrar, en la confirmación) o en un destino del
  outbox.
- Ver el **outbox en vivo** mientras se tumba una base de datos con Docker.
- Ejecutar la **recuperación** (reconciliador y recolector) al momento.
- Verificar los **invariantes de consistencia** y seguir la **bitácora de la
  saga** de cada compra.

## Cómo ejecutarlo

Requiere el backend con la inyección de fallas habilitada (`backend/.env`):

```
FAULT_INJECTION_ENABLED=true
```

`scripts/start-dev.ps1` lo levanta automáticamente junto con la tienda. A mano:

```powershell
cd laboratorio
npm install
npm run dev     # http://localhost:5174
```

Ingresa con una cuenta de administrador (`admin@tiendaya.gt` / `password123`).
