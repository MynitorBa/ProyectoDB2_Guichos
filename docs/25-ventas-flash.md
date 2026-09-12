# Ventas flash por vendedor

## Regla de negocio

Una promoción flash pertenece a una **oferta MySQL**, por lo que también queda
asociada al vendedor dueño de esa oferta. El vendedor define el precio, las
unidades y las fechas; no puede promocionar ofertas ajenas. Solo puede existir
una promoción programada o activa por oferta.

Al crearla, sus unidades pasan de stock normal a `cantidad_reservada`. No se
duplica inventario: `cantidad_disponible` continúa siendo el saldo físico total
y el stock comprable normalmente es
`cantidad_disponible - cantidad_reservada`.

## Responsabilidad de cada base

- **MySQL** es la verdad durable: `promociones_flash`, `reservas_flash`, oferta,
  vendedor, inventario, pedido y movimientos de auditoría.
- **Redis** decide atómicamente qué compradores obtienen las unidades cuando
  hay concurrencia. Mantiene el contador y las reservas temporales.
- El carrito Redis guarda el token de la reserva, pero el checkout vuelve a
  validar y bloquear en MySQL antes de cobrar.

Una reserva dura cinco minutos, permite como máximo una unidad promocional por
usuario y es idempotente. Al vencer devuelve el cupo al contador flash. Al
comprar, el pedido conserva el precio promocional y la reserva queda
`convertida`. Al finalizar o cancelar la promoción, las unidades no vendidas
se liberan para compras normales.

El vencimiento efectivo es `min(hora de reserva + 5 minutos, finaliza_en)`.
Por tanto, una reserva creada tres minutos antes del cierre dura únicamente
tres minutos. El carrito muestra una cuenta regresiva y distingue una reserva
vencida de un artículo que realmente se quedó sin stock.

El worker `flash_sale_worker.py` activa, vence y finaliza promociones cada
segundo. Si Redis se reinicia, reconstruye el contador y las reservas vigentes
desde MySQL. La finalización durable sigue funcionando aunque Redis esté
temporalmente caído.

## Instalación

`scripts/setup.ps1` y `scripts/start-dev.ps1` ejecutan automáticamente
`backend/scripts/apply_flash_sales.py`. Para aplicarlo manualmente desde
`backend/`:

```powershell
.\venv\Scripts\python.exe scripts\apply_flash_sales.py
```

Después se reinicia FastAPI para cargar los routers y el worker.

## Prueba funcional

1. Iniciar sesión como vendedor y abrir **Mis ofertas**.
2. Entrar a una oferta propia activa, crear una venta flash y comprobar que el
   stock normal se reduce por las unidades apartadas.
3. Como comprador, abrir ese producto. Deben aparecer vendedor, precio normal,
   precio flash, unidades y cuenta regresiva.
4. Reservar una unidad. El carrito debe mostrar la etiqueta **Venta flash**, no
   permitir cambiar la cantidad y conservarla durante cinco minutos.
5. Completar el checkout. El pedido debe usar el precio flash y la reserva debe
   quedar convertida en MySQL.
6. Cancelar otra promoción desde el panel del vendedor y comprobar que las
   unidades no vendidas regresan al stock normal.

## Descubrimiento en el catálogo

La navegación secundaria evita repetir todas las categorías y ofrece accesos a
**Todos los productos**, **Ofertas flash**, **Más vendidos**, **Novedades** y
**Vender en TiendaYa**. El catálogo admite filtrar solamente promociones y
ordenarlas por descuento.

Para cada producto se comparan las ofertas normales disponibles y las
promociones vigentes. Una promoción solo se presenta como precio principal si
su precio efectivo es menor que cualquier precio normal disponible. La tarjeta
muestra precio anterior, descuento, vendedor, unidades y cuenta regresiva. La
sección de inicio desaparece cuando no existe ninguna promoción ganadora.

Prueba automática principal:

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest tests\test_flash_sales.py tests\test_checkout.py tests\test_redis_cart.py -q
```

La prueba concurrente enfrenta 100 compradores contra 10 unidades y exige
exactamente 10 reservas exitosas, sin sobreventa.
