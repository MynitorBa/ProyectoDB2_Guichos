# TiendaYa: estado y pendientes de la rama de fraude

Estado al 19 de octubre de 2026. Este documento distingue implementación de
validación: los problemas pendientes no se consideran resueltos por publicar la
rama.

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

- **Datos DEMO comprobados:** 13 líneas apuntan a ofertas de otro vendedor;
  seis subtotales de subpedido no coinciden con sus líneas; las ofertas #149 y
  #150 carecen de inventario; la auditoría I7 halló siete divergencias de
  stock en Elasticsearch. No se alteraron pedidos, inventario ni proyecciones
  para ocultar esas diferencias. `verify_setup.py` no detecta actualmente
  ofertas sin inventario.
- **Lógica general:** se comprobó y corrigió un defecto del generador DEMO:
  resolver ofertas por SKU global confundía vendedores. Hay prueba de
  regresión. No está demostrado que las inconsistencias comerciales anteriores
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
