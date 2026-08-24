# Pruebas funcionales integrales

Fecha de ejecución: 24 de agosto de 2026
Entorno: aplicación local, MySQL y MongoDB de desarrollo.

## Resultado general

- Backend: **31 pruebas automatizadas aprobadas**.
- Frontend: **compilación de producción aprobada** (2,634 módulos).
- API: salud, autenticación, catálogo, pedidos, paneles, historial y exportación operativos.
- Integración MongoDB + MySQL: 65 productos comprobados y 0 discrepancias de lectura dual.
- Datos funcionales: el pedido de prueba `#96` se conserva intencionalmente y el inventario de la oferta `#8` quedó en 44 unidades.

## Matriz funcional

| Área | Resultado | Evidencia principal |
|---|---|---|
| Inicio y catálogo | Aprobado | 65 productos, paginación, categorías, destacados y búsqueda exacta. |
| Detalle de producto | Aprobado | Precio, inventario, vendedor, atributos e imágenes cargan correctamente. |
| Autenticación | Aprobado | Comprador, vendedor y administrador inician sesión con sus permisos. |
| Protección de rutas | Aprobado | Comprador redirigido fuera de `/admin`; API devuelve 403 al rol incorrecto. |
| Perfil y direcciones | Aprobado | Datos y dos direcciones visibles; validación de campos obligatorios activa. |
| Carrito | Aprobado | Agregar producto, contador y cálculos de subtotal, IVA y total correctos. |
| Checkout | Aprobado | Pedido `#96`, snapshots, pago, subpedido, movimiento y outbox creados. |
| Inventario | Aprobado | Oferta `#8`: 45 → 44; la suite de pruebas no modificó ese valor. |
| Factura PDF | Aprobado | HTTP 200, `application/pdf`, nombre correcto y 2,804 bytes. |
| Pedidos del comprador | Aprobado parcial | Lista y detalle global funcionan; falta mostrar los subpedidos por vendedor. |
| Panel vendedor | Aprobado | Solo muestra sus subpedidos y bloquea pedidos ajenos con HTTP 403. |
| Estados del vendedor | Corregido | La versión nueva expone `confirmado`, `preparando`, `enviado`, `entregado`. |
| Notificaciones | Aprobado | Aviso de nueva venta y marcado como leído comprobados. |
| Panel administrador | Aprobado | Estadísticas, productos, categorías, usuarios, ventas y pedidos cargan. |
| Exportación de ventas | Aprobado | Excel HTTP 200, MIME XLSX correcto, 9,326 bytes. |
| Historial de producto | Aprobado | 8 eventos y reconstrucción histórica en versión 8. |
| Registro | Aprobado parcial | Validaciones de formulario comprobadas; no se creó una cuenta residual. |
| Correo de factura | No ejecutado | SMTP no está configurado; se evitó enviar correo externo real. |

## Defectos encontrados y corregidos

### 1. Limpieza destructiva de pruebas de checkout

La fixture eliminaba todos los pedidos con ID mayor que 30. Esto podía borrar pedidos reales creados durante el uso local. Ahora registra y elimina exclusivamente los IDs creados por cada prueba, y restaura su inventario y proyección MongoDB.

Comprobación posterior:

- Antes: 31 pedidos, máximo ID 96, stock oferta 8 = 44.
- Después de las 31 pruebas: los mismos 31 pedidos, ID 96 presente y stock = 44.

### 2. Estado “En preparación” ausente

La API del vendedor consultaba el enum del pedido global y el frontend usaba `en_preparacion`, mientras el subpedido realmente utiliza `preparando`. Se corrigieron ambos lados y se añadió una prueba específica.

La instancia temporal con el código nuevo respondió:

```text
confirmado, preparando, enviado, entregado
```
### 3. Prueba de migración incompatible con el uso real

Una prueba exigía exactamente 29 movimientos de inventario. Una compra legítima elevó el total a 30 y causó un falso fallo. Ahora se valida el mínimo migrado y, principalmente, que todas las referencias mantengan integridad.

## Pendientes reales

1. Reiniciar el backend activo del puerto 8000 para que cargue la corrección del estado `preparando`. El código nuevo ya fue comprobado en un servidor temporal.
2. Incluir `pedido_vendedores` en el detalle que recibe el comprador y mostrar un bloque de envío/estado por vendedor. Actualmente solo se presenta el estado global.
3. Configurar una cuenta SMTP de la empresa antes de probar el envío real de facturas por correo.

## Comandos de regresión

Desde la raíz del repositorio:

```powershell
.\backend\venv\Scripts\python.exe -m pytest backend\tests -q
cd frontend
npm run build
```
