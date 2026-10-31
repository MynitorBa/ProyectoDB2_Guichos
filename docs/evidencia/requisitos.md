# Verificación del sistema completo contra el enunciado

Generado por `backend/scripts/verificar_requisitos.py` el 2026-10-30 19:15 contra el sistema en marcha (API, motores y servicio de embeddings). Cada fila es una prueba en vivo, una consulta a la base de datos o la comprobación de un documento exigido; lo que modifica datos de forma no trivial se cita por la prueba de integración o el escenario de falla que lo cubre.

**Resultado: 37 de 37 requisitos obligatorios cumplidos.**

| ID | Entrega | Requisito | Cómo se verificó | Resultado | Detalle |
|---|---|---|---|---|---|
| FI-1 | Fase inicial | Modelo relacional normalizado: usuarios, direcciones, categorías, productos, pedidos y líneas, pagos e inventario | Tablas en MySQL | OK | 44 tablas; incluye categorias, direcciones, inventario, ofertas, pagos, pedido_lineas, pedidos, producto_referencias, usuarios |
| FI-2 | Fase inicial | Diagrama entidad-relación y justificación de la normalización | Documentos | OK | docs/02-diagrama-ER.md, docs/01-modelo-relacional.md |
| FI-3 | Fase inicial | Compra como transacción atómica: pedido, líneas, pago y descuento de inventario | Pruebas de integración | OK | Prueba de integración: test_checkout.py::test_checkout_exitoso, test_checkout.py::test_checkout_sin_stock, test_checkout.py::test_concurrencia_ultima_unidad |
| FI-4 | Fase inicial | DDL versionado y datos de prueba representativos | Archivos + conteos | OK | 16 usuarios, 71 productos, 199 pedidos |
| FI-5 | Fase inicial | Registro e inicio de sesión con roles comprador, vendedor y administrador | API en vivo | OK | contraseña débil rechazada (422); registro + login de un usuario nuevo (luego eliminado); roles: admin=['comprador', 'vendedor', 'administrador']; vendedor1=['comprador', 'vendedor']; comprador1=['comprador'] |
| E1-1 | Entrega 1 | Catálogo por categoría; cada categoría muestra solo sus atributos | API en vivo | OK | 13 categorías con esquema propio; filtro por categoría → 3 productos |
| E1-2 | Entrega 1 | Alta y edición de producto desde el panel, con formulario según la categoría | API + pruebas | OK | GET /admin/products 200 |
| E1-3 | Entrega 1 | Vista de detalle de producto | API en vivo | OK | Laptop Dell Inspiron 15: 2 oferta(s), atributos ['procesador', 'ram_gb', 'almacenamiento', 'pulgadas'] |
| E1-4 | Entrega 1 | Estado de un producto en una fecha anterior (precio, descripción, disponibilidad) | API en vivo | OK | estado reconstruido con claves ['nombre', 'descripcion', 'disponible', 'atributos', 'estado', '_reconstruido_al']; 27 eventos en el historial |
| E1-5 | Entrega 1 | Migración de productos a la base documental, documentada y reproducible | Script + documento | OK | backend/scripts/migrate_products_to_mongo.py, docs/09-plan-migracion-incremental.md |
| E1-6 | Entrega 1 | Embeber o referenciar: reseñas, imágenes y producto–vendedor | Documento | OK | docs/04-ADR-002-embeber-vs-referenciar.md |
| E1-7 | Entrega 1 | Al menos un índice compuesto según un patrón de consulta | Índices de MongoDB | OK | idx_categoria_disponible_precio, idx_texto_nombre_descripcion, idx_categorias_estado |
| E1-8 | Entrega 1 | Al menos una consulta con el marco de agregación | API en vivo (aggregate) | OK | GET /admin/stats/catalog (catalog_service.stats_catalogo usa aggregate) |
| E1-9 | Entrega 1 | Historial como registro de eventos y reconstrucción por fecha | MongoDB + API | OK | 172 eventos en producto_eventos (sin sobrescribir); reconstrucción en E1-4 |
| E1-10 | Entrega 1 | Líneas de pedido (MySQL) referencian productos de MongoDB | Documento + datos | OK | 252/252 líneas con producto_ref; docs/07-referencia-sql-mongo.md |
| E2-1 | Entrega 2 | Carrito en clave-valor con expiración explícita por inactividad | API en vivo | OK | TTL 1800 s (configurado 1800 s); doc 24-carrito-redis.md |
| E2-2 | Entrega 2 | Oferta de inventario limitado con operaciones atómicas, sin sobreventa bajo concurrencia y sin bloqueos de aplicación | Pruebas de integración + API | OK | Prueba de integración: test_flash_sales.py::test_cien_compradores_compiten_por_diez_unidades, test_flash_sales.py::test_reintento_del_mismo_usuario_es_idempotente, test_checkout.py::test_checkout_flash_convierte_reserva_y_descuenta_pool |
| E2-3 | Entrega 2 | Panel de manipulación de reseñas (grafo, consulta de varios saltos) | API en vivo | OK | resumen de reglas: ['bombardeo', 'bombardeo_historico', 'reviewer_unico_vendedor', 'reviewer_unico_vendedor_historico', 'cluster_coordinado', 'cluster_coordinado_historico']; cluster de cuentas 200 |
| E2-4 | Entrega 2 | Panel de ventas por intervalos de tiempo y productos en ascenso (columnar) | API en vivo | OK | 6 productos con tendencia semanal (Cassandra) |
| E2-5 | Entrega 2 | Comparación grafos vs. columnar y condiciones para la no seleccionada | Documento | OK | docs/26-decision-grafos-columnar.md |
| E3-1 | Entrega 3 | Búsqueda de texto libre con tolerancia ortográfica y relevancia | API en vivo | OK | «macbok» → MacBook Air M2 |
| E3-2 | Entrega 3 | Filtros facetados calculados con agregaciones del motor | API en vivo | OK | facetas: ['categorias', 'vendedores', 'precio', 'disponibilidad', 'atributos'] |
| E3-3 | Entrega 3 | Autocompletado o corrección ortográfica | API en vivo | OK | «sams» → Samsung Galaxy A54; sugerencia para «samsng galaxi»: samsung galaxy |
| E3-4 | Entrega 3 | Mapping deliberado (no el por defecto) | Archivo + índice | OK | productos_v2.json: dynamic strict, analizadores propios, dense_vector |
| E3-5 | Entrega 3 | Estrategia de consistencia del checkout (componentes, puntos de falla, mitigación) | Documento | OK | docs/30-estrategia-consistencia-checkout.md |
| E3-6 | Entrega 3 | Prueba de falla simulada y comportamiento comunicado al usuario | Escenarios E00–E17 (demo_fallas.py) | OK | docs/evidencia/fallas/README.md (18 escenarios marcados como cumplidos) |
| E3-7 | Entrega 3 | Opcional: evaluación de migrar pagos a NewSQL | Documento | OK | docs/52-ADR-007-evaluacion-newsql-pagos.md: evaluación analítica, decisión de no migrar |
| F-1 | Entrega final | Recomendación por similitud semántica de la descripción (página de producto) | API en vivo | OK | similares por vectores: ['Laptop ASUS VivoBook', 'Laptop HP Pavilion 1', 'Laptop Lenovo IdeaPa']; inicio: 8 productos |
| F-2 | Entrega final | Búsqueda semántica mediante representaciones vectoriales | API en vivo | OK | «algo para escuchar música sin cables» → ['Airpods Pro 2da genera', 'Audífonos Sony WH-1000'] (alternativa semanticos) |
| F-3 | Entrega final | Autenticación y autorización en un componente NoSQL, con evidencia de que un usuario sin permisos no puede salir de su alcance | verificar_permisos.py (40 intentos) | OK | 40/40 como se esperaba. Evidencia en docs\evidencia\permisos.md (Redis, MongoDB y Elasticsearch) |
| F-4 | Entrega final | Diagrama de arquitectura final con todos los componentes de persistencia | Archivos | OK | docs/diagramas/arquitectura-final.svg/.png y docs/05 |
| F-5 | Entrega final | Retrospectiva: decisiones que se sostienen y que se replantean | Documento | OK | docs/49-retrospectiva.md |
| F-6 | Entrega final | Informe de arquitectura final | Archivos | OK | docs/informe/*.pdf y .docx, docs/informe-entrega4.md |
| T-1 | Transversal | Panel administrativo: catálogo, pedidos, inventario y reportes | API en vivo | OK | catálogo 200, pedidos 200, reportes 200, inventario (ofertas) 200 |
| L-1 | Lineamientos | Registro de decisión por cada componente: contexto, alternativas (incluida no cambiar), decisión, justificación y consecuencias | Estructura de los documentos | OK | 6 registros con los cinco campos |
| L-2 | Lineamientos | Repositorio único con historial incremental | git log | OK | 98 commits |
| L-3 | Lineamientos | Documentación con instrucciones para poner en marcha el sistema completo | README | OK | README.md |
