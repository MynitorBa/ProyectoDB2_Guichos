# Imágenes SQL, categorías múltiples y revisión de ofertas

**Fecha:** 25 de agosto de 2026  
**Rama:** `revision-modelo-relacional-ferxo`

## Cambio recibido y revisión

El commit del equipo incorporó carga de imágenes como BLOB, varias categorías
por producto, prefijos para generar SKU, perfil de vendedor y administración
de ofertas. Antes de activarlo se detectó que faltaba el DDL correspondiente y
que el selector de ofertas enviaba `usuario_id` aunque el backend esperaba
`vendedores.id`. También el nuevo formato de imágenes podía dejar las tarjetas
sin imagen.

## Ajustes incluidos

- Migración incremental e idempotente
  `database/mysql/12_catalog_images_categories.sql`.
- `producto_imagenes` guarda `LONGBLOB`, MIME y orden con FK a
  `producto_referencias`.
- `producto_referencia_categorias` representa la clasificación N:M y conserva
  la categoría principal.
- `categorias.sku_prefix` es único cuando tiene valor.
- El instalador aplica la extensión en bases migradas y nuevas.
- El endpoint de vendedores distingue `usuario_id` de `vendedor_id`.
- Las ofertas validan precio positivo, stock no negativo y SKU de hasta 50
  caracteres; su proyección MongoDB se recalcula desde la oferta principal.
- La carga acepta JPG, PNG, WEBP y GIF reales, hasta 5 MB.
- El catálogo filtra tanto la categoría principal como las secundarias y las
  tarjetas aceptan imágenes antiguas `{url}` o URL de texto.
- Si falla MySQL al crear un producto, se compensa la escritura MongoDB para no
  dejar un documento huérfano.

## Evidencia local

- 65 referencias MySQL y 65 documentos MongoDB, sin huérfanos.
- 65 relaciones de categoría principal creadas.
- 65/65 proyecciones comerciales sincronizadas.
- Carga y lectura real de un PNG de 185,768 bytes: HTTP 200; el registro de
  prueba fue eliminado al terminar.
- Login administrador, listado de vendedores y ofertas: HTTP correcto.
- Una oferta con precio y stock negativos devuelve HTTP 422 y no escribe datos.
- Catálogo visual: 65 productos, 12 tarjetas en la primera página, imágenes
  visibles y cero errores de consola.
- `pytest`: 37 pruebas aprobadas.
- `npm run build`: compilación aprobada.

## Qué debe probar el equipo

1. Ejecutar `scripts/setup.ps1` sobre una copia de sus datos.
2. Entrar como administrador y crear un producto asignando vendedor, dos
   categorías y una imagen.
3. Confirmar en DBeaver el BLOB y sus FKs, y en MongoDB únicamente la URL.
4. Agregar una segunda oferta de otro vendedor y verificar que precio/stock del
   catálogo correspondan a la oferta activa principal.
5. Editar categorías e imágenes y comprobar que no haya errores de consola.
6. Ejecutar `backend/scripts/verify_setup.py`, las pruebas y el build.

El flujo posterior de solicitudes de vendedores se documenta en
[`21-solicitudes-catalogo-vendedores.md`](21-solicitudes-catalogo-vendedores.md).
