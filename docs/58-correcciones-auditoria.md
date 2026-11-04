# Correcciones de la auditoría del 1 de noviembre

La auditoría estática del equipo («Hallazgos y propuestas de mejora», sobre el commit `1b9e9dd` de la rama
`feature/ferxo-cassandra-planb-outbox`) encontró nueve hallazgos. Cada uno se contrastó con el código antes de
tocar nada. Este documento dice cuáles eran ciertos, qué se cambió, dónde y por qué, y qué prueba demuestra el
arreglo. Fecha: 4 de noviembre de 2026.

## 0. Integración del plan B de Cassandra

La rama de Ferxo partía del último commit de `inicio-entrega4` (`d05920e`), así que entró sin conflictos de
Git (avance rápido). Se aplicó su migración 27 y su carga inicial (`apply_respaldo_analitica.py`,
`backfill_mysql_analytics.py --apply-if-needed`), como lo hace `setup.ps1`.

La suite completa, que su cierre técnico reconocía no haber ejecutado, encontró **una prueba desactualizada**:
`test_checkout_por_oferta_crea_subpedido_y_snapshots` enumera las filas del outbox de una compra y no incluía
el nuevo destino `analitica_mysql`. Se agregó. Además, el laboratorio de consistencia conoce el destino nuevo
(nombre en el panel del outbox y punto de falla `outbox.analitica_mysql`).

## 1. Veredicto por hallazgo

| ID | ¿Cierto? | Qué se hizo |
|---|---|---|
| H-01 Ledger PRINCIPAL/DEMO | Sí; además se encontró la causa | Ledger explícito en cada arranque y control de identidad en I6 |
| H-02 Pruebas sin aislamiento | Sí, por diseño | Candado: la suite no corre si algún motor apunta a la DEMO |
| H-03 37/37 sin ejecutar pruebas | Sí | El verificador ejecuta las pruebas que cita y registra commit y base |
| H-04 I6 limitado a 1 000 cobros | Sí (hoy 129 cobros) | Recorrido completo por páginas; si se trunca, «no verificable» |
| H-05 Imágenes de reseñas | Sí: el único defecto de código | Validación completa antes de escribir y limpieza ante cualquier falla |
| H-06 Doble caída Cassandra + MongoDB | Sí | Se documenta como limitación (decisión del equipo) |
| H-07 I7 verde sin Elasticsearch | Sí | Invariantes con tres estados; «no verificable» nunca cuenta como cumplido |
| H-08 Documentos sin el plan B de Cassandra | Sí | Diagrama, docs 05/44/49, README e informe actualizados (con adenda) |
| H-09 «Única fuente de verdad» | A medias (docs/05 ya decía «transaccional») | Se precisó en el informe y en docs/05 |

## 2. Correcciones de código

### H-05 · Subida de imágenes de reseñas

- **Antes:** `POST /reviews/{id}/imagenes` leía cada archivo sin límite de tamaño, aceptaba cualquier contenido
  con extensión de imagen y lo escribía en disco **antes** de comprobar que la reseña fuera del usuario o que no
  se pasara de cuatro imágenes. Solo limpiaba los archivos ante dos tipos de error. La imagen sin seguimiento que
  aparecía en `backend/static/reviews/` es consistente con ese comportamiento.
- **Dónde:** `backend/app/api/v1/reviews.py`.
- **Cómo:** primero se valida todo sin escribir nada: dueño de la reseña, cupo de cuatro imágenes y cada archivo
  con `image_service.read_valid_image` (máximo 5 MB y firma de bytes real, la misma validación de las demás
  cargas del proyecto). Después se escriben los archivos y, si cualquier paso posterior falla (también un error
  de MySQL), se deshace la transacción y se borran los archivos escritos.
- **Por qué así:** validar antes de escribir es más simple y seguro que intentar limpiar después; la limpieza
  queda solo para lo que puede fallar después de escribir. Se reutilizó la validación que ya existía en lugar de
  escribir otra.
- **Prueba:** `tests/test_resena_imagenes.py` (7 pruebas): imagen válida, más de 5 MB, extensión falseada,
  reseña ajena, segundo archivo inválido, más de cuatro imágenes y falla de MySQL después de escribir.
  **Contra el código anterior, 4 de las 7 fallan**; con la corrección pasan todas.

### H-07 y H-04 · Invariantes «no verificables»

- **Antes:** I7 respondía «cumple» aunque Elasticsearch no hubiera respondido (solo lo decía en el detalle), el
  resumen contaba un invariante sin verificar como cumplido, e I6 pedía solo los 1 000 cobros más recientes.
- **Dónde:** `backend/app/services/consistency_service.py`, `payment_simulator/app.py`,
  `backend/scripts/verificar_consistencia.py`, `laboratorio/src/paneles.jsx`.
- **Cómo:** cada invariante tiene tres estados: cumple (`True`), violado (`False`) y no verificable (`None`). Una
  revisión parcial sin violaciones queda en «no verificable». El resumen trae `ok` (solo si todos se
  verificaron y se cumplen), `violado` y `no_verificables`. I6 recorre todo el libro de la pasarela por páginas
  de 1 000 (la pasarela acepta `desde` y ordena de forma estable); si alcanza el tope de 100 páginas, el resultado
  es «no verificable». `verificar_consistencia.py` sale con 0 (todo verificado), 1 (violado) o 2 (incompleto) y
  el laboratorio muestra el estado intermedio en ámbar.
- **Por qué así:** un verificador que dice «todo bien» sin haber mirado todo es peor que uno que dice «no pude
  mirar»: se puede tomar una decisión con base en una falsa seguridad. No se bloquea ninguna compra por esto; es
  solo diagnóstico.
- **Prueba:** `tests/test_invariantes_verificables.py`: un cobro discrepante que queda fuera de la primera página
  se detecta; un recorrido truncado queda «no verificable»; I7 sin Elasticsearch nunca sale cumplido; el resumen
  no cuenta lo no verificable.

### H-01 · Ledger de la pasarela por entorno

- **Causa encontrada:** `scripts/demo-environment.ps1` arrancaba la pasarela de la DEMO (puerto 8006) **sin**
  `PASARELA_DB`, así que escribía los cobros de la DEMO en `payment_simulator/ledger.db`, el de la instancia
  principal. Es la mezcla que vio la auditoría. En el equipo de Mynor ese cobro no está en `ledger.db` e I6 se
  cumple (129 cobros revisados).
- **Dónde:** `scripts/start-dev.ps1`, `start-main-safe.ps1`, `switch-ti-endaya-environment.ps1` y
  `demo-environment.ps1`; `payment_simulator/app.py`; `consistency_service.py`.
- **Cómo:** cada arranque fija `PASARELA_DB` (la principal `ledger.db`, la DEMO `ledger.demo.db`). La pasarela
  informa en `GET /control` qué ledger usa, e I6 se niega a comparar la base de un entorno con el ledger del otro:
  responde «no verificable: configuración inválida».
- **Por qué así:** se corrige la causa y además se pone un control que la detectaría si volviera a pasar. No se
  movió, borró ni reembolsó ningún cobro existente, como pide la auditoría.
- **Prueba:** I6 con base principal y ledger DEMO (y al revés) queda «configuración inválida»; la pasarela de las
  pruebas informa su ledger temporal.

### H-02 · La suite no corre contra la DEMO

- **Cierto, pero por diseño:** las pruebas son de integración contra las bases de `backend/.env` (así está
  documentado desde la Entrega 3) y cada fixture restaura solo lo que toca.
- **Dónde:** `backend/tests/conftest.py` (`senales_de_demo`, `pytest_sessionstart`).
- **Cómo:** antes de recolectar cualquier prueba, se revisan los seis motores; si alguno apunta a la DEMO (sus
  puertos o nombres de `backend/.env.demo`), pytest termina con código 2 sin escribir nada.
- **Por qué no una pila TEST completa:** la VM de Docker (5.8 GB) no admite ni la principal y la DEMO a la vez;
  una tercera pila con seis motores no cabe. El candado protege lo que de verdad importa (los datos de la
  presentación) con un costo mínimo.
- **Prueba:** una corrida real de pytest con MySQL de la DEMO termina con código 2 y sin ejecutar pruebas.

### H-03 · El 37/37 ejecuta lo que cita

- **Dónde:** `backend/scripts/verificar_requisitos.py`.
- **Cómo:** los requisitos que se demuestran con pruebas de integración ahora **las ejecutan** en la misma
  corrida (7 pruebas) y cumplen solo si pasan; antes solo se comprobaba que existieran. La matriz registra la
  fecha, el commit, la base y cómo se verificó cada fila (API en vivo, pruebas ejecutadas o documento).
- **Por qué:** una prueba presente no es una prueba ejecutada.

## 3. Documentación (H-08, H-09)

- `docs/diagramas/arquitectura-final.svg/.png`: Cassandra en el recuadro del plan B y el destino
  `analitica_mysql` en el outbox.
- `docs/05`: responsabilidad de MySQL precisada («única fuente de verdad **transaccional**; el contenido del
  catálogo lo decide MongoDB»), destino nuevo en el flujo y Cassandra en la tabla del plan B.
- `docs/44`: Cassandra ya tiene plan B y enlaza a los documentos 53–57.
- `docs/49`: la retrospectiva de Cassandra se actualiza con el resultado: las tablas resumen en MySQL que
  proponía son justamente su plan B, y respondieron más rápido con estos datos.
- `README.md`: el respaldo de las tendencias y los enlaces a 53–58.
- Informe final: se corrigieron las imprecisiones y se agregó una **adenda fechada** con lo hecho después del
  30 de octubre, sin reescribir las cifras de ese corte.

## 4. Lo que no se hizo y por qué

| Propuesta | Decisión |
|---|---|
| Pila TEST aislada con los seis motores | No cabe en la memoria de Docker; el candado de H-02 cubre el riesgo principal |
| Tolerar la caída simultánea de Cassandra y MongoDB (H-06) | Queda documentada como limitación: los paneles de tendencias de vendedor y «sin ventas» siguen leyendo nombres de MongoDB |
| Optimizaciones O-01 a O-06 | Sin medición que muestre un cuello de botella, como recomienda la propia auditoría |
| Autoría del informe (D-05) | Decisión del equipo: la portada se cambia en `docs/informe/generar_informe_entrega4.py` |

## 5. Verificación

Suite completa de integración, sin el backend de desarrollo encendido: **439 pruebas pasan, 4 omitidas, 0 fallan** (eran 415 antes de la auditoría; se agregaron las del plan B de Cassandra, `test_resena_imagenes.py` y `test_invariantes_verificables.py`).

| Verificación | Resultado |
|---|---|
| Requisitos del enunciado (con las pruebas citadas ejecutadas) | 37/37 |
| Invariantes I1–I7 | Todos verificados y cumplidos (I6 con 129 cobros, I7 con MongoDB y Elasticsearch) |
| Permisos mínimos | 40/40 |
| `verify_setup` | Setup completo |
| Build del laboratorio | Sin errores |

Una lección operativa: la suite no debe correr con el backend de desarrollo encendido. Sus workers (outbox,
reconciliador) actúan sobre la misma base y la misma pasarela que las pruebas: en una corrida así hubo un
deadlock real entre la limpieza de una prueba y el consumidor del outbox, y el reconciliador resolvió un pedido
que una prueba estaba observando. Sin el backend encendido, esas mismas pruebas pasan.
