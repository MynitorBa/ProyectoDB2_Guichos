# TiendaYa: estado y pendientes de la rama de fraude

Estado actualizado al 19 de octubre de 2026. Este documento distingue implementación de
validación: los problemas pendientes no se consideran resueltos por publicar la
rama.

**Nota de cierre:** los pasos de reconstrucción y `seed-full` descritos abajo
quedan suspendidos para Entrega 3. El estado operativo y la matriz de revisión
vigentes están en [41-cierre-funcional-entrega3.md](41-cierre-funcional-entrega3.md).

## Implementado

- Arquitectura de seis motores: MySQL para transacciones, MongoDB para catálogo,
  Redis para carrito y reservas, Cassandra para analítica temporal, Neo4j para
  relaciones y fraude, y Elasticsearch para búsqueda.
- Sincronización mediante Outbox por destino, saga de checkout y verificación de
  compras/pagos antes de proyectar evidencia.
- Detección F01–F07, con análisis manual y worker horario configurable. F07
  distingue coincidencias únicas de casos ambiguos.
- Panel administrativo de investigación con contadores, registros, evidencias,
  paginación, filtros, búsqueda, ordenamiento y conservación de decisiones y
  notas humanas.
- Generador reproducible de datos sintéticos; entorno DEMO con bases, puertos y
  volúmenes independientes, y scripts para alternar entre PRINCIPAL y DEMO.
  Se corrigió la resolución de ofertas del generador para usar
  variante/vendedor, ya que distintos vendedores pueden compartir SKU.

## Validación efectiva

- En DEMO medium: 1,630 pedidos, 2,503 líneas, 742 reseñas y 2,376 compras
  pagadas proyectadas. Seis motores saludables; Neo4j quedó con 2,376 compras
  y sin la proyección huérfana previamente identificada.
- Panel F01–F07 probado visualmente. Conteos posteriores a la corrección
  temporal: 1, 0, 32, 95, 9, 32 y 2 expedientes activos respectivamente; F07
  conserva siete coincidencias ambiguas. No se observaron huellas duplicadas
  y se conservó una decisión humana de descarte.
- El historial temporal faltante de las ofertas DEMO #149 y #150 se reparó
  desde sus propios datos, tras respaldo restaurado y verificado;
  `verify_setup.py` terminó correctamente. El detalle está en
  `docs/39-panel-fraude-f07-demo.md`.
- En la última regresión se ejecutaron 58 pruebas: 55 aprobadas (35 focalizadas
  no destructivas, cuatro sobre una restauración MySQL aislada y 16 adicionales
  de lectura) y tres fallidas por inconsistencias de datos DEMO descritas abajo.
  Dos pruebas de escritura se excluyeron deliberadamente. La compilación del
  frontend y las pruebas visuales del panel se habían completado en la fase
  anterior.

## Problemas conocidos y alcance

- **Datos DEMO aún pendientes:** 13 líneas apuntan a ofertas de otro vendedor;
  seis subtotales de subpedido no coinciden con sus líneas; las ofertas #149 y
  #150 carecen de inventario. No se alteraron pedidos ni saldos para ocultar
  esas diferencias. `verify_setup.py` no detecta actualmente ofertas sin
  inventario.
- **Proyección resuelta:** siete divergencias de stock en Elasticsearch se
  corrigieron reindexando exclusivamente esos documentos desde MySQL y MongoDB,
  que ya concordaban. I7 pasó luego para los 285 productos, sin eventos Outbox
  pendientes. El índice anterior de esos siete documentos tiene respaldo fuera
  de Git.
- **Lógica general:** se comprobó y corrigió un defecto del generador DEMO:
  resolver ofertas por SKU global confundía vendedores. Hay prueba de
  regresión. También se corrigió el seed incremental para no añadir líneas a
  pedidos existentes ni descontar stock olvidando ventas de corridas previas.
  Estos cambios no reescribieron datos ya generados. No está demostrado que las inconsistencias comerciales anteriores
  afecten datos de la instancia PRINCIPAL ni que provengan de la lógica de
  checkout; requieren auditoría separada.
- **Validación pendiente:** la suite completa recolecta 199 pruebas, pero no se
  ha certificado. Varias escriben o reconstruyen motores y no deben ejecutarse
  contra DEMO viva ni PRINCIPAL. `seed-full` tampoco se ha ejecutado.

## Próximos pasos

1. Auditar y corregir con respaldo las inconsistencias comerciales DEMO, sin
   inventar registros históricos ni modificar PRINCIPAL.
2. Validar y reconciliar las proyecciones frente a sus fuentes autoritativas.
3. Preparar aislamiento de los seis motores y ejecutar la suite completa.
4. Ejecutar `seed-full` solo cuando integridad y recursos lo permitan.
5. Validar nuevamente el resultado y entonces preparar la integración de rama;
   este push no fusiona con `main` ni con `entrega3-mynor`.

## Investigación posterior al commit (sin commit ni push)

La auditoría identificó las trece líneas afectadas: 404, 499, 798, 893, 1044,
1139, 1438, 1533, 1684, 1891, 2014, 2211 y 2334. Sus importes y
subpedidos corresponden a las ofertas #149/#150 de los vendedores #7/#8, pero
apuntan a #96/#97 de los vendedores #13/#14, que comparten SKU. Las salidas
de inventario están cargadas a #96/#97 y las trece compras Neo4j conservan
esos IDs de oferta. Cambiar solo la FK dejaría proyecciones y saldos
incoherentes. Las ofertas #149/#150 no tienen registro de apertura de stock;
el generador pretendía crear 5,000 unidades por oferta, pero los saldos de
#96/#97 tampoco concilian hoy con todos sus movimientos (4,984 frente a 4,981,
y 4,991 frente a 4,989). No se fabricó un saldo inicial ni se transfirieron
ventas sin una reconciliación transaccional y multiproyección completa.

En los seis subpedidos #162, #191, #219, #228, #233 y #236, una línea añadida
en la ampliación de perfil excede el total y el pago originales. Las líneas
adicionales son #286, #345, #400, #418, #428 y #434. Dos de ellas (#418 y
#428) ya respaldan reseñas y varias tienen movimientos/proyecciones. Por eso
ni elevar los totales ni borrar únicamente esas líneas sería una reparación
segura. El generador quedó protegido para no repetir el defecto, pero las
relaciones históricas DEMO siguen pendientes de una corrección coordinada.

Respaldo MySQL DEMO restaurado en un esquema temporal aislado (40 tablas y
conteos de líneas/movimientos coincidentes):
`_backups/demo-integrity/tiendaya_demo_pre_integrity_20261019_185559.sql`,
SHA-256 `FF2796919264A0A0EA6013E82AF48B9528CF0EE2496025AC0FF446843645618F`.
Respaldo de los siete documentos Elasticsearch:
`_backups/demo-integrity/elasticsearch_7_pre_reindex_20261019.json`, SHA-256
`871E7902118E6062B4723A8D516C2819600AD3E75F667FA6095F84749935CD51`.
Ambos están fuera de Git.

Regresión de esta investigación: 23 pruebas unitarias/focalizadas aprobadas;
tres pruebas de lectura comercial aún fallan por los defectos pendientes.
`verify_setup.py` aprobó e I1–I5 e I7 aprobaron; I6 quedó no verificable porque
la pasarela DEMO no estaba iniciada. El análisis F01–F07 no se volvió a
ejecutar; las 44 alertas existentes conservaron huellas únicas y la decisión
humana del expediente #15. PRINCIPAL permaneció detenida y sin cambios.
