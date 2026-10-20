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
| En producción | Sí | No; los controles de inyección no se registran si la bandera está deshabilitada |

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

En la presentación de Entrega 3, `scripts/start-presentation.ps1` inicia el
laboratorio original en `http://localhost:5174` sobre la API DEMO en `:8000`.
Con `FAULT_INJECTION_ENABLED=false`, el login, Outbox, invariantes y bitácora
son de solo lectura; los controles de fallas se muestran deshabilitados. No
activar la inyección sobre la DEMO original solo para hacer una prueba.

Para ejercitar los controles de fallas se requiere un entorno aislado con
respaldo y `FAULT_INJECTION_ENABLED=true`:

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
