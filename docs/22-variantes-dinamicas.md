# Variantes dinámicas de producto

**Estado:** implementado el 29 de agosto de 2026.

## Decisión

Una variante representa una combinación vendible del mismo producto. Sus
atributos son dinámicos: pueden ser `ram`, `capacidad`, `color`, `talla` o
cualquier otra dimensión pertinente a las categorías del producto. No existen
columnas fijas de color o talla.

MongoDB `producto_variantes` es la autoridad documental de la variante:

- `producto_ref`: producto general al que pertenece;
- `sku_catalogo`: identificador automático de la combinación;
- `atributos`: objeto dinámico con solo los valores diferenciadores;
- `clave_variante`: representación canónica que evita duplicados aunque cambie
  el orden de las claves;
- `estado`, `es_predeterminada` y fechas.

MySQL conserva únicamente `producto_variante_referencias(id,
producto_referencia_id, variante_ref, fecha_registro)`. Esta tabla puente
permite que `ofertas.producto_variante_id` tenga una FK real sin duplicar los
atributos documentales. La unicidad `(vendedor_id, producto_variante_id)`
impide dos ofertas vigentes equivalentes del mismo vendedor, pero permite que
el vendedor ofrezca varias combinaciones del mismo producto.

## Flujo

1. Todo producto previo recibe una variante predeterminada vacía.
2. El administrador puede crear combinaciones con pares atributo/valor.
3. Una oferta nueva debe seleccionar una variante concreta.
4. Una solicitud de vendedor también identifica la variante solicitada.
5. El detalle público agrupa las ofertas por variante y después permite elegir
   vendedor/precio.
6. Carrito, checkout, pedido y factura continúan usando `oferta_id`; por ello el
   precio y el inventario siguen protegidos transaccionalmente en MySQL.

## Instalación y verificación

`scripts/setup.ps1` ejecuta `backend/scripts/apply_dynamic_variants.py`. El
proceso crea un respaldo, instala las FKs e índices, genera variantes
predeterminadas y enlaza las ofertas existentes. Es idempotente y aborta si no
puede determinar sin ambigüedad la variante de una oferta.

Comprobaciones disponibles:

```powershell
backend\venv\Scripts\python.exe backend\scripts\verify_setup.py
backend\venv\Scripts\python.exe backend\scripts\smoke_dynamic_variants.py
```

La prueba de humo crea una variante temporal mediante la API, comprueba su
lectura pública y la elimina al finalizar.
