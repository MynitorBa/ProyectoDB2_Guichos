# Carrito activo en Redis

## Responsabilidades

- **Redis** conserva la intención temporal de compra: ofertas, cantidades,
  precio observado al agregar y una referencia al producto. La clave
  `carrito:{usuario_id}` expira tras `REDIS_CART_TTL` segundos sin actividad.
- **MySQL** sigue siendo la autoridad de ofertas, precios e inventario. El
  checkout bloquea esas filas y guarda snapshots definitivos en el pedido.
- **MongoDB** aporta la descripción del producto para mostrar el carrito; no
  interviene en el cobro ni en la disponibilidad.

El precio guardado en Redis nunca se cobra directamente. Si difiere del precio
actual de MySQL, la API responde `PRICE_CHANGED`; la pantalla refresca el total
y exige otra confirmación con los precios que el usuario acaba de ver.

## Atomicidad y concurrencia

Agregar, actualizar y eliminar ítems se implementa con scripts Lua. Cada script
modifica el HASH y renueva su TTL como una única operación atómica. Así, dos
solicitudes concurrentes no pierden incrementos por una secuencia separada de
lectura y escritura.

## Checkout seguro

1. La API lee el carrito del usuario autenticado desde Redis. La lista enviada
   por el navegador se conserva solo por compatibilidad y no es autoritativa.
2. Si Redis no está disponible, el checkout se detiene antes de escribir en
   MySQL y responde `503 CART_UNAVAILABLE`.
3. MySQL valida usuario y dirección, bloquea ofertas e inventario y confirma el
   pedido en una transacción.
4. Después del commit se elimina el carrito. Si esa limpieza falla, se registra
   el error, pero una venta ya confirmada no se presenta falsamente como un 500.

La idempotencia distribuida completa ante reintentos posteriores a una caída es
parte de la entrega dedicada a consistencia distribuida.

## Instalación y comprobación

Desde la raíz:

```powershell
.\scripts\setup.ps1
.\scripts\start-dev.ps1
```

La interfaz de inspección está en <http://localhost:8082>. Para validar:

```powershell
cd backend
.\venv\Scripts\python.exe scripts\verify_setup.py
.\venv\Scripts\python.exe -m pytest tests -q
```

La migración `scripts/migrate_cart_to_redis.py` es idempotente, completa
`producto_ref` cuando puede resolverlo desde la oferta y marca como abandonados
los carritos SQL ya procesados, incluidos los vacíos.
