# Cierre funcional de Entrega 3 — revisión del 19 de octubre de 2026

Esta revisión se limita a los requisitos de [informe-entrega3.md](informe-entrega3.md).
No certifica la integridad histórica de la DEMO medium original ni convierte la
DEMO limpia interrumpida en un conjunto medium válido. No se ejecutaron compras,
fallas provocadas, seeds ni reconstrucciones durante esta revisión.
El informe original está fechado el 6 de octubre y sus 162 pruebas son un
resultado histórico, no el conteo certificado de la rama actual.

## Estado operativo para demostración

Se reactivaron los seis contenedores **originales** de la DEMO, cada uno con
su volumen `tiendaya_demo_demo_*`; los seis quedaron saludables. La pila limpia
incompleta está detenida y conserva sus volúmenes `tiendaya_demo_clean_*`.
Frontend `:5175`, API `:8005` y pasarela simulada `:8006` respondieron 200.
Para esta revisión de solo lectura la API se inició con `--lifespan off`:
no se lanzaron los workers de Outbox, promociones ni recuperación del checkout.
La pasarela está encendida, pero **no se probó un cobro actual**. La instancia
PRINCIPAL sigue detenida e intacta.

## Matriz de cumplimiento

| Requisito | Implementación y responsable | Evidencia | Comprobación actual | Pendiente indispensable |
|---|---|---|---|---|
| Búsqueda tolerante a errores y por relevancia | `backend/app/services/search_service.py`, `backend/app/api/v1/search.py`, `frontend/src/components/layout/SearchBar.jsx` | [Comparación de búsqueda](evidencia/busqueda-comparacion.md), [diseño](29-busqueda-elasticsearch.md), pruebas `test_search_api.py` | En la DEMO original, `macbok` encontró MacBook Air M2, sin degradación; índice disponible. La comparación 17/17 es evidencia histórica, no una nueva ejecución. | Ninguno para esta consulta; repetir la batería completa solo en entorno controlado. |
| Facetas, filtros, autocompletado y búsqueda por tienda; degradación sin Elasticsearch | `search_service.py`, `backend/app/api/v1/search.py`, `frontend/src/pages/CatalogPage.jsx` y `SearchBar.jsx` | [Informe](informe-entrega3.md), pruebas `test_search_api.py`, [E11](evidencia/fallas/E11.md) | Categoría `computadoras`: 27 resultados; búsqueda en tienda: 1 resultado; autocompletado: 1 producto; detalle de producto: 200. La degradación se apoya en E11; no se detuvo Elasticsearch ahora. | Navegación visual manual, porque el navegador integrado bloqueó el acceso automatizado a localhost. |
| Checkout distribuido: oferta, carrito, inventario, cobro, idempotencia, compensación y recuperación | `backend/app/api/v1/cart.py`, `orders.py`, `backend/app/services/checkout_service.py`, pasarela `payment_simulator/` | [Estrategia](30-estrategia-consistencia-checkout.md), pruebas `test_checkout_saga.py` y `test_checkout_recovery.py`, [E00–E09](evidencia/fallas/README.md) | Código y pruebas presentes; la evidencia de 14 escenarios es histórica. No se ejecutaron pruebas de escritura contra las bases vivas. | Para una demostración transaccional nueva, usar una base de pruebas aislada y coherente. |
| Outbox por destino y convergencia ante caídas | `backend/app/services/outbox_service.py`, `backend/app/api/v1/sync.py` | [E10–E13](evidencia/fallas/README.md), `test_outbox_v2.py` | Consumidores y pruebas presentes; no se provocaron fallas ni reintentos nuevos. | Ninguno para revisar la evidencia existente; repetición en vivo requiere entorno aislado. |
| Prueba de falla simulada y explicación de recuperación | `backend/scripts/demo_fallas.py`, `laboratorio/`, `backend/scripts/verificar_consistencia.py` | Los 14 archivos [E00–E13](evidencia/fallas/README.md) están presentes | Compilación del laboratorio correcta; no se ejecutó el script porque escribe datos y detiene servicios. | Ninguno para la evidencia ya documentada. |
| F01–F07, panel de investigación, decisiones humanas y automatización | `backend/app/services/fraud_detection_service.py`, `fraud_analysis_worker.py`, `backend/app/api/v1/reviews.py`, `frontend/src/pages/AdminPage.jsx` | [Panel y F07](39-panel-fraude-f07-demo.md); pruebas `test_fraud_f07.py` y `test_fraud_automation.py` | API original: F01=1, F02=0, F03=32, F04=95, F05=9, F06=32 y F07=2 activos; 44 alertas totales, páginas de 10, evidencia F07 presente. Sin token, acceso 403. Expediente #15 conserva la decisión `descartada`; el respaldo confirma que no tenía nota. Prueba visual anterior histórica. | Verificar visualmente la pantalla antes de exponerla; no usar los conteos de la DEMO parcial. |

## Corrección focalizada del generador

En `backend/scripts/seed_demo_large.py`, los patrones F07 consultaban compras
pagadas de perfiles anteriores, pero el mapa recibido solo cubría las ofertas
del perfil actual. La oferta #136 existía y tenía inventario; faltaba en ese
mapa. La función `complete_paid_line_inventory_ids` recupera de MySQL los
inventarios de las ofertas pagadas ausentes y falla de forma explícita si
alguna oferta realmente carece de inventario. Dos pruebas aisladas cubren el
caso recuperable y el error real. **No se volvió a ejecutar seed-medium**, por
lo que el arreglo está probado de forma aislada, no por integración completa.

## Verificaciones de esta revisión

- 26 pruebas focalizadas no destructivas aprobadas: guardas del seed,
  correlación F07, automatización de fraude y definición del índice.
- 29 pruebas HTTP de búsqueda aprobadas sobre la DEMO original, sin escribir
  datos. Una aserción antigua esperaba únicamente SKU `TECH-CEL-*` para
  `telefono`; el catálogo DEMO añade celulares con SKU `DEMO-*`. Se corrigió
  la prueba para verificar la categoría `celulares`, sin cambiar el buscador.
- Compilación de `frontend/` y `laboratorio/`: correcta.
- `git diff --check`: sin errores de whitespace.
- Presencia confirmada de los 14 expedientes E00–E13 y de los scripts de
  demostración, consistencia y recuperación.
- Login de administrador correcto; endpoint de sincronización con cinco
  destinos y cero problemas reportados. La salud del índice confirmó
  `productos_v1_20261019161417`.
- El navegador integrado rechazó la inspección automatizada de localhost por
  su política de URL. Las comprobaciones actuales de pantalla se limitaron a
  API y compilación; no se eludió esa restricción.
- No se ejecutó la suite completa: incluye pruebas que modifican bases vivas.

## Pendientes clasificados

**Bloquean declarar una nueva prueba end-to-end de checkout ahora:** la API
se dejó en modo lectura sin workers y no se ejecutó una compra. Para repetir
esa demostración hay que habilitar el arranque normal en un entorno de pruebas
controlado. La DEMO limpia sigue a medio `seed-medium` y no debe usarse para
demostraciones. La DEMO original sí está disponible para navegación y consulta,
pero sus inconsistencias sintéticas conocidas impiden declararla íntegra.

**Mejoras no bloqueantes para revisar la entrega:** comprobar visualmente el
panel en un navegador del equipo y repetir checkout en entorno aislado;
reconciliar la DEMO limpia y documentar su
integridad cuando se retome la generación. Las inconsistencias comerciales de
la DEMO original permanecen documentadas en
[40-estado-proyecto-y-pendientes.md](40-estado-proyecto-y-pendientes.md).

**Trabajo posterior:** `seed-full`, ampliación del dataset, nuevas reglas de
fraude y cualquier alcance de Entrega 4. Nada de ello se requiere para revisar
las evidencias actuales de Entrega 3.

## Guion para compañeros

1. Leer [informe-entrega3.md](informe-entrega3.md): requisitos y decisiones.
2. Mostrar la búsqueda tolerante a `macbok`, facetas y autocompletado en un
   entorno con índice coherente; verificar que precio y stock provienen de MySQL.
3. Explicar el checkout con [la estrategia](30-estrategia-consistencia-checkout.md)
   y los expedientes [E00–E13](evidencia/fallas/README.md), especialmente E02,
   E03, E08 y E11. No correr `demo_fallas.py` sobre una DEMO viva compartida.
4. Mostrar el panel F01–F07 con [su guía](39-panel-fraude-f07-demo.md),
   aclarando que las alertas son indicios explicables, no bloqueos de venta.
5. No presentar la DEMO limpia parcial como medium terminado ni sus conteos
   como validación de las proyecciones finales.

**Conclusión:** GO para presentar búsqueda, panel, arquitectura y evidencia
documental de Entrega 3 con la DEMO original; NO-GO para afirmar que se repitió
ahora una compra o una recuperación end-to-end, ni para usar la DEMO limpia
parcial. Este informe no autoriza modificar datos durante la presentación.
