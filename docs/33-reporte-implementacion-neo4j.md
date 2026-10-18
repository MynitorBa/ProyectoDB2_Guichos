# Reporte de implementación definitiva de Neo4j

Fecha de trabajo: 17 de octubre de 2026. Rama local: `entrega3-mynor`.

Este reporte distingue lo implementado de lo comprobado. No sustituye el
procedimiento de instalación ni autoriza eliminar el modelo heredado.

## Fase 0 — Auditoría y protección

- Se preservaron los cambios locales que ya existían.
- La línea base comprobada antes del corte contenía 42 reseñas, 77 líneas
  pagadas válidas y 78 relaciones `COMPRO`; una relación era heredada sobrante.
- Se preparó respaldo JSON previo a la migración en `backups/reviews/`.
- No se reinicializaron volúmenes ni se eliminaron registros históricos.

## Fase 1 — Autoridad de reseñas

- `database/mysql/21_review_authority.sql` amplía `resenas` y crea las tablas
  durables de imágenes y respuestas.
- MySQL impone `UNIQUE(usuario_id, producto_referencia_id, vendedor_id)`.
- La elegibilidad exige una línea del mismo usuario, producto y vendedor, pago
  aprobado y pedido no cancelado ni reembolsado.
- Se permite editar la reseña existente, no crear otra para la misma combinación.
- Cancelar o reembolsar revalida el respaldo sin borrar la reseña.
- API, detalle de producto, imágenes, respuestas, moderación y calificaciones
  de búsqueda leen desde MySQL. Neo4j recibe la proyección mediante outbox.

Conciliación local aplicada: 42 reseñas conservadas; 17 tenían compra pagada
atribuible y 25 quedaron pendientes/no verificadas. No existían imágenes ni
respuestas heredadas que migrar en esta instancia.

## Fase 2 — Grafo definitivo

Modelo nuevo:

```text
Usuario -REALIZO-> Compra -DE_PRODUCTO-> Producto
                         -A_VENDEDOR-> Vendedor
Usuario -GESTIONA-> Vendedor -OFRECE-> Producto
Usuario -ESCRIBIO-> Reseña -SOBRE-> Producto
                            -CALIFICA_A-> Vendedor
                            -BASADA_EN-> Compra
```

- `Compra.linea_id` es único.
- `OFRECE` conserva identificadores, variante, SKU y estado, nunca precio o stock.
- Compras, cancelaciones, ofertas y reseñas se sincronizan idempotentemente por
  el outbox; una caída de Neo4j no bloquea checkout ni reseñas MySQL.
- El backfill es reconstruible desde MySQL y MongoDB.

Conciliación local aplicada: 77 nodos `Compra`, 72 relaciones `OFRECE`, 42
reseñas y 17 relaciones `BASADA_EN`. `COMPRO` continúa temporalmente para no
romper evidencias heredadas; retirarla requiere autorización expresa y una
última comprobación de consumidores.

## Fase 3 — Recomendaciones

- `GET /api/v1/products/{producto_ref}/recommendations` implementa compradores
  comunes contando usuarios distintos.
- Excluye el producto consultado y, en recomendaciones personalizadas, los ya
  comprados por el usuario.
- MySQL revalida oferta activa, precio y stock. Si Neo4j falla, responde una
  lista vacía y la tienda continúa funcionando.
- El detalle del producto muestra la sección solo cuando existen resultados.

## Fase 4 — Fraude explicable

- La migración `22_fraud_alerts.sql` crea expedientes deduplicados y revisables.
- Se detectan autocompras por `GESTIONA`, frecuencia, volumen y concentración
  respecto a las unidades pagadas de la oferta.
- Se correlacionan movimientos de inventario dentro de ±3 días, movimientos
  realizados por el propietario y reseñas respaldadas por esas compras.
- Inventario atípico exige evidencia combinada; vender y reponer normalmente no
  basta para abrir una alerta.
- Las alertas almacenan motivos, evidencia, prioridad y estado administrativo.
  Nunca suspenden cuentas, cancelan pedidos ni cambian stock automáticamente.

## Fase 5 — Ventas flash y cierre

- Neo4j recibe `promocion_flash_id` únicamente en líneas convertidas y pagadas.
- Se pueden consultar las líneas históricas y el resumen por promoción:
  compradores distintos, unidades, ofertas y concentración máxima por comprador.
- `verify_setup.py` concilia compras, ofertas y reseñas respaldadas contra MySQL,
  además de verificar la autoridad y unicidad de reseñas.

## Evidencia de pruebas

- Compilación Python de los módulos modificados: aprobada.
- Nueve pruebas nuevas de modelo, unicidad, atribución a vendedor,
  recomendaciones, fraude, ventas flash y rutas de outbox: aprobadas.
- Build de producción del frontend: aprobado.
- `setup.ps1` y `verify_setup.py` terminaron en `Setup completo` con 77 compras,
  72 ofertas, 42 reseñas y 17 respaldos `BASADA_EN` proyectados en Neo4j.
- `verificar_consistencia.py` confirmó los siete invariantes, incluida la
  comparación entre MySQL y el libro de la pasarela simulada.
- La diferencia Cassandra 78 / Neo4j 77 no es una divergencia: Cassandra
  conserva además la línea 106 del pedido reembolsado 96 para calcular ingresos
  reembolsados y netos; Neo4j proyecta únicamente las 77 compras pagadas que
  siguen vigentes. No se alteró la proyección Cassandra durante este cierre.
- La suite integral terminó con **171 pruebas aprobadas y 0 fallos**.
- La compilación final de Vite procesó 3060 módulos y terminó correctamente.

## Comandos finales de comprobación

Desde la raíz:

```powershell
.\scripts\setup.ps1
cd backend
.\venv\Scripts\python.exe scripts\verify_setup.py
.\venv\Scripts\python.exe -m pytest tests -q
cd ..\frontend
npm run build
```

No se creó commit ni se hizo push durante esta implementación.
