# Solicitudes de catálogo de vendedores

**Fecha:** 25 de agosto de 2026  
**Rama:** `revision-modelo-relacional-ferxo`

## Regla funcional

Un vendedor verificado puede proponer contenido comercial, pero no publicarlo.
El panel separa explícitamente dos operaciones:

- **Producto nuevo:** nombre, descripción, categorías, atributos, imágenes,
  precio, stock y comentario.
- **Oferta de producto existente:** producto, precio, stock y comentario. No
  acepta imágenes porque estas pertenecen al producto, no a la oferta del
  vendedor.

Los SKU no son editables. El producto recibe el prefijo configurado en su
categoría principal y un identificador hexadecimal único; las ofertas reciben
un SKU comercial derivado automáticamente del producto y del vendedor. La
creación administrativa y la aprobación usan el mismo servicio generador.

La solicitud permanece `pendiente` y no aparece en el catálogo. El
administrador puede aprobarla o rechazarla con observaciones. El vendedor puede
consultar su historial, cancelar una solicitud pendiente y recibe una
notificación después de la revisión.

## Persistencia y aprobación

La migración `database/mysql/13_catalog_requests.sql` crea:

- `solicitudes_catalogo`, cabecera, datos comerciales, decisión y resultados;
- `solicitud_catalogo_categorias`, clasificación de propuestas de producto;
- `solicitud_catalogo_imagenes`, relación ordenada con los BLOB temporales;
- `producto_imagenes.subida_por`, propiedad de la carga previa a aprobación.

Al aprobar un producto nuevo se crea el documento MongoDB, la referencia y las
categorías SQL, se asignan sus imágenes, y se crean oferta, precio inicial e
inventario. Si la parte SQL falla, se compensa el documento y sus eventos en
MongoDB. Al aprobar una oferta existente solo se crea o reactiva la oferta y su
inventario; el outbox actualiza la proyección comercial MongoDB.

## API y permisos

Rutas del vendedor bajo `/api/v1/vendor/catalog-requests`:

- `POST /images`, `DELETE /images/{id}`;
- `POST /products`, `POST /offers`;
- `GET /`, `PATCH /{id}/cancel`.

Rutas administrativas bajo `/api/v1/admin/catalog-requests`:

- `GET /` con filtros de estado y tipo;
- `POST /{id}/approve`, `POST /{id}/reject`.

La API verifica rol, perfil de vendedor, estado `verificado`, propiedad de las
imágenes, categorías activas, producto existente, generación de SKU, precio y
stock. También impide solicitudes u ofertas vigentes duplicadas para el mismo
vendedor y producto.

Los atributos se validan contra todos los esquemas de las categorías
seleccionadas. El backend rechaza atributos obligatorios ausentes, tipos
incorrectos y campos ajenos a esos esquemas.

## Evidencia funcional

- Migración aplicada de forma idempotente y 10 llaves foráneas verificadas.
- Propuesta real de producto con imagen aprobada: creó documento, referencia,
  oferta e inventario y notificó al vendedor; los datos de prueba se retiraron.
- Solicitud real de oferta rechazada: fue visible al administrador, conservó el
  motivo en el historial y notificó al vendedor; los datos de prueba se
  retiraron.
- Las solicitudes de oferta rechazan el campo de imágenes por contrato.
- Los conteos de referencias SQL y documentos MongoDB permanecen alineados y
  las pruebas automáticas no dejan solicitudes ni productos temporales.
- `pytest`: 43 pruebas aprobadas; `verify_setup.py`: instalación completa;
  `npm run build`: compilación de producción aprobada.
- Control de acceso real: comprador bloqueado en rutas de vendedor y vendedor
  bloqueado en revisión administrativa (HTTP 403).
- Producto de dos categorías aprobado con diez atributos y SKU automático;
  oferta existente aprobada con SKU derivado automáticamente.
- Selector común probado en navegador: búsqueda textual, filtrado sin acentos,
  desplazamiento y cero errores de consola.

## Qué debe probar el equipo

1. Ejecutar `scripts/setup.ps1` y `backend/scripts/verify_setup.py`.
2. Iniciar sesión como vendedor verificado y proponer un producto con varias
   categorías e imagen.
3. Confirmar que no se muestre en el catálogo antes de aprobarlo.
4. Aprobarlo desde el panel administrador y confirmar producto, oferta, stock e
   imagen tanto en la interfaz como en MySQL/MongoDB.
5. Solicitar una oferta para un producto existente y confirmar que el formulario
   no solicite imágenes.
6. Rechazar otra solicitud con observaciones y comprobar historial y
   notificación del vendedor.
7. Confirmar que un vendedor no pueda revisar solicitudes ni manipular imágenes
   cargadas por otra cuenta.
