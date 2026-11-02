# Plan B de Cassandra — implementación y estado

## Decisión

Cassandra sigue siendo el motor principal de tendencias. MySQL conserva la
autoridad de pedidos, pagos e inventario y aloja tres tablas derivadas para
responder las mismas consultas cuando Cassandra no está disponible. El contenido
nativo del catálogo continúa bajo autoridad de MongoDB.

Las tablas `analitica_productos_semana`,
`analitica_productos_vendedor_semana` y `analitica_ofertas_vendedor_semana`
corresponden a los resúmenes usados por la API. Se indexan por semana y por
producto, vendedor u oferta según la consulta. Las semanas inician el lunes en
horario de Guatemala. El mismo extractor de líneas pagadas que alimenta
Cassandra determina reembolsos, unidades flash e importes del respaldo.

La migración 27 crea esas tablas, `analitica_respaldo_control` y el destino
`analitica_mysql` del Outbox. Una actualización comercial encola destinos
independientes para Cassandra y MySQL. El trabajador de MySQL recalcula la
semana afectada desde pedidos y pagos y la reemplaza en una transacción. Un
reintento repite el cálculo sin duplicar importes. La copia inicial se realiza
con `backfill_mysql_analytics.py --apply`, después de respaldar MySQL. Hasta
que termine, la API no presenta el respaldo como estadísticas válidas.
La migración también añade, si falta, un índice sobre `pedidos.fecha_creacion`
para que el recálculo semanal no recorra todos los pedidos históricos.

La API mantiene los permisos del administrador y vendedor, identifica el motor
en `fuente_datos` y usa el detector de fallas existente. Si Cassandra falla,
consulta MySQL; si tampoco hay respaldo listo, responde 503. La interfaz
advierte del retraso eventual. La recuperación de Cassandra usa su propia fila
pendiente del Outbox, sin depender del estado de la proyección MySQL.

## Instalación incremental

1. Verificar instancia, puertos y volúmenes. Respaldar MySQL y comprobar la
   restauración en una base aislada.
2. Aplicar primero las migraciones pendientes 24, 25 y 26. Configurar el
   control de acceso de Entrega 4 sin sobrescribir contraseñas existentes.
3. Aplicar únicamente `backend/scripts/apply_respaldo_analitica.py`.
4. Ejecutar `backend/scripts/backfill_mysql_analytics.py --dry-run`, revisar
   cantidades y luego `--apply`.
5. Comparar ambos motores por las mismas semanas, productos y vendedores antes
   de habilitar el modo degradado como demostración.

No ejecutar `scripts/setup.ps1` para este cambio incremental: además de las
migraciones ejecuta backfills, reparaciones, reindexación e instalación de
dependencias. No reconstruir Cassandra para instalar el respaldo.

## Límites de esta fase

El recálculo lee las líneas elegibles de la semana afectada. A mayor actividad,
su costo crece con las ventas de esa semana; debe medirse antes de aplicar una
política de mayor frecuencia. Las imágenes del respaldo solo conservan las ya
copiadas a MySQL; el indicador de fuente y los importes no dependen de MongoDB.

### Verificación local, 1 de noviembre de 2026

Antes de aplicar las migraciones se exportó MySQL y MongoDB y se comprobó su
restauración en bases temporales: 39 tablas y 7 colecciones con conteos iguales.
Las migraciones 24–27 se aplicaron en PRINCIPAL sin alterar pedidos ni pagos.
El backfill del respaldo analítico tomó 78 líneas elegibles y 23 semanas.
Quedaron 73 filas de producto/semana, 75 de vendedor/producto/semana y 75 de
oferta/vendedor/semana. Al comparar con Cassandra por clave y métricas
(unidades, ingresos, reembolsos, pedidos, ofertas y flash), hubo **0 diferencias**
en las tres proyecciones. Para la semana del 14 de septiembre, la respuesta
completa de `admin/trends` coincidió entre ambos motores: 13 productos con las
mismas cifras, comparaciones e imágenes. Una consulta directa del servicio con
un vendedor existente también obtuvo su reporte desde MySQL en una caída
simulada del detector. La prueba HTTP de autenticación pasó: administrador y
vendedor consultaron sus tendencias (13 y 9 filas, respectivamente), y el
vendedor recibió 403 al intentar acceder a las estadísticas administrativas.

Los siete servicios (seis motores y embeddings) respondieron correctamente.
El índice de Elasticsearch se migró de v1 a v2 con 66 documentos y 66 vectores;
el índice v1 se conservó para poder revertir el alias. La API de productos
similares devolvió `origen: vectores`. `verify_setup.py` informó configuración
completa y el frontend compiló. La verificación de consistencia general detectó
un cargo aprobado histórico en el archivo local de la pasarela sin pedido
correspondiente en PRINCIPAL (invariante I6). La investigación de lectura del
informe 56 confirmó su pedido, pago y saga en DEMO: el verificador estaba
comparando un ledger con la base de otro entorno. No se alteró el cargo ni
afecta la conciliación Cassandra–MySQL descrita arriba.

La comparación de rendimiento en dos motores aislados, los escenarios A/B/C
y sus límites se detallan en `docs/55-benchmark-cassandra-vs-mysql-planb.md`.
No se midió el checkout completo ni se identificó saturación general.
