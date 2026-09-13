# Decisión de Entrega 2: grafos frente a base columnar

## Decisión

TiendaYa implementa **Apache Cassandra** como base distribuida orientada a
columnas anchas para análisis de demanda por intervalos de tiempo. Esta
decisión corresponde a la Entrega 2 según el enunciado oficial del curso.

## Comparación

| Criterio | Grafo | Cassandra |
|---|---|---|
| Fortaleza principal | Recorrer relaciones de profundidad variable | Leer grandes volúmenes por una clave de partición conocida |
| Consulta natural | Productos comprados juntos, afinidades, recomendaciones | Ventas por producto, vendedor y semana; comparación entre periodos |
| Modelo | Nodos, aristas y propiedades | Tablas diseñadas por consulta, particiones y clustering |
| Ajuste al requisito actual | Menor: todavía no se solicita recomendación | Alto: se pide identificar cambios de demanda entre periodos |
| Costo operacional | Añade otro motor para una función futura | Resuelve directamente los reportes temporales actuales |

No se seleccionó una base de grafos porque el caso evaluado en esta entrega es
temporal y agregado, no un recorrido de relaciones. Un grafo sería adecuado
más adelante para recomendaciones como “usuarios que compraron X también
compraron Y”, pero no reemplaza la autoridad transaccional de MySQL ni mejora
por sí solo el reporte semanal requerido.

## Límites de responsabilidad

- **MySQL** confirma pagos, inventario, pedidos, líneas, vendedores y ofertas.
- **MongoDB** describe productos, variantes, atributos e imágenes de catálogo.
- **Redis** conserva carrito y reservas efímeras de ventas flash.
- **Cassandra** mantiene una proyección reconstruible para analítica; nunca
  aprueba pagos ni descuenta inventario.

La selección evita trasladar lógica transaccional a Cassandra. Los datos se
publican después de guardar la venta en MySQL mediante el outbox, por lo que
una indisponibilidad analítica no bloquea una compra.
