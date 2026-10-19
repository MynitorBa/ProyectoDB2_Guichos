# TiendaYa — Validación de seed-medium y fraude F01–F06

Fecha: 19 de octubre de 2026

Entorno: `tiendaya_demo`

Esta validación no ejecutó `seed-full`, no modificó TiendaYa principal, no implementó F07 y no alteró umbrales de fraude.

## 1. Resultado de seed-medium

| Entidad | Conteo |
|---|---:|
| Usuarios | 665 |
| Vendedores | 36 |
| Productos | 285 |
| Ofertas conservadas | 430 |
| Pedidos | 1,630 |
| Líneas de pedido | 2,503 |
| Pagos | 1,630 |
| Reseñas | 742 |
| Movimientos de inventario | 2,587 |
| Líneas pagadas proyectadas | 2,376 |

Las 430 ofertas incluyen combinaciones válidas de la etapa small que se conservaron porque ya estaban vinculadas a pedidos. La ampliación del perfil no eliminó ni reasignó esos datos históricos.

## 2. Diferencia entre líneas MySQL y Cassandra

La diferencia es `2,503 - 2,376 = 127` líneas. No es una inconsistencia:

| Clasificación | Pedido | Pago | Líneas | Elegible para Cassandra |
|---|---|---|---:|---|
| Compra pagada | Entregado | Aprobado | 2,373 | Sí |
| Compra pagada | Enviado | Aprobado | 3 | Sí |
| Compra cancelada | Cancelado | Rechazado | 121 | No |
| Pago sin confirmar | Pendiente | Pendiente | 3 | No |
| Pago sin confirmar | Confirmado | Pendiente | 3 | No |

La proyección exige pago `aprobado` o `reembolsado`. Un pedido cancelado solo permanece como analítica cuando posee pago reembolsado. Por eso las 127 líneas excluidas no deben contarse como compras pagadas.

## 3. Reconciliación F04

La auditoría individual encontró exactamente:

- 17 reseñas académicas originales con usuario, producto, vendedor, línea y pago aprobado demostrables.
- 25 reseñas académicas históricas sin evidencia suficiente.

Antes de aplicar se creó un respaldo completo de MySQL DEMO:

- Archivo: `C:\Users\fboan\Documents\ChatGPT\Proyecto Base de datos\_backups\demo-f04\tiendaya_demo_pre_f04_20261019_101757.sql`
- Tamaño: 2,309,545 bytes.
- SHA-256: `58D0300ED8EAE2FB1CB0B2D2D50FC94F5ECF8AF4AE66C99881451B1C784A5040`.

Resultado posterior:

| Grupo | Verificadas | No verificadas |
|---|---:|---:|
| Reseñas base | 17 | 25 |
| Reseñas sintéticas medium | 630 | 70 |
| Total | 647 | 95 |

Las 647 reseñas verificadas poseen `pedido_linea_id`; ninguna quedó verificada sin evidencia. Neo4j contiene exactamente 647 relaciones `BASADA_EN`.

## 4. Nuevo análisis F01–F06

Ejecución manual número 3:

- Estado: exitosa.
- Origen: manual.
- Duración: 1,063 ms.
- Corrida manual small de referencia: 500 ms.
- Variación: +563 ms; 2.13 veces la duración small.

| Indicador | Small observado | Medium después de F04 | Explicación |
|---|---:|---:|---|
| F01 bombardeo | 1 | 1 | El escenario concentrado se conserva |
| F01 histórico | 0 | 0 | No se usan reseñas históricas como señal pública |
| F04 sin compra verificada | 52 antes de reconciliar | 95 | 25 históricas base + 70 escenarios sintéticos medium no verificados |
| F02 reseña a un único vendedor | 3 | 0 | Con el dataset ampliado, los usuarios proyectados ya no cumplen exclusividad suficiente |
| F02 histórico | 0 | 0 | Sin señal histórica pública |
| F03 grupo coordinado | 10 | 20 | El perfil medium incorpora más coincidencias coordinadas |
| F03 histórico | 0 | 0 | Sin señal histórica pública |
| F05 autocompra | 9 | 9 | Se conservan las nueve señales dentro de la ventana móvil |
| F06 inventario atípico | 20 | 32 | Se conservan 20 ofertas small y aparecen 12 combinaciones vendedor-oferta nuevas |

F01–F04 son indicadores informativos. F05 y F06 crean expedientes persistentes en MySQL.

## 5. Expedientes F05

Todos los compradores coinciden con el propietario actual del vendedor, todos los pedidos están entregados, todos los pagos están aprobados y cada expediente tiene una reseña verificada vinculada. No existe todavía historial temporal de propiedad; por eso la atribución sigue siendo indicativa.

| Alerta | Comprador/propietario | Vendedor | Oferta | Producto | Pedido/línea | Cantidad | Fecha UTC | Reseña | Concentración |
|---:|---|---|---:|---|---|---:|---|---|---:|
| 1 | usuario 17 | DEMO Tienda 001 | 91 | Producto DEMO 0025 | 56/70 | 2 | 24-sep 06:52 | `v:25` | 33.33% |
| 2 | usuario 19 | DEMO Tienda 003 | 93 | Producto DEMO 0027 | 58/72 | 2 | 22-sep 06:50 | `v:27` | 22.22% |
| 3 | usuario 21 | DEMO Tienda 005 | 87 | Producto DEMO 0021 | 52/66 | 2 | 28-sep 06:56 | `v:21` | 22.22% |
| 4 | usuario 21 | DEMO Tienda 005 | 95 | Producto DEMO 0029 | 60/74 | 2 | 20-sep 06:48 | `v:29` | 40.00% |
| 5 | usuario 23 | DEMO Tienda 007 | 89 | Producto DEMO 0023 | 54/68 | 2 | 26-sep 06:54 | `v:23` | 40.00% |
| 6 | usuario 16 | DEMO Tienda 000 | 90 | Producto DEMO 0024 | 55/69 | 1 | 25-sep 06:53 | `v:24` | 12.50% |
| 7 | usuario 18 | DEMO Tienda 002 | 92 | Producto DEMO 0026 | 57/71 | 1 | 23-sep 06:51 | `v:26` | 25.00% |
| 8 | usuario 20 | DEMO Tienda 004 | 94 | Producto DEMO 0028 | 59/73 | 1 | 21-sep 06:49 | `v:28` | 20.00% |
| 9 | usuario 22 | DEMO Tienda 006 | 88 | Producto DEMO 0022 | 53/67 | 1 | 27-sep 06:55 | `v:22` | 16.67% |

Los nueve expedientes mantienen prioridad informativa y huellas distintas. El medium no creó duplicados F05.

## 6. Expedientes F06

Todos los expedientes contienen tres ajustes positivos del propietario, con cantidades individuales 25, 35 y 45 y motivos `Ajuste positivo DEMO F06 #1`, `#2` y `#3`. La suma comprobada es 105 en los 32 casos.

| Alerta | Oferta | Vendedor | Producto | Movimientos | Primera → última fecha | Pares temporales | Estado |
|---:|---:|---|---|---|---|---:|---|
| 10 | 66 | DEMO Tienda 000 | Producto DEMO 0000 | 259–261 | 17-oct 07:17 → 19-oct 07:17 | 3 | pendiente |
| 11 | 67 | DEMO Tienda 001 | Producto DEMO 0001 | 262–264 | 17-oct 06:17 → 19-oct 06:17 | 0 | pendiente |
| 12 | 68 | DEMO Tienda 002 | Producto DEMO 0002 | 265–267 | 17-oct 05:17 → 19-oct 05:17 | 0 | pendiente |
| 13 | 69 | DEMO Tienda 003 | Producto DEMO 0003 | 268–270 | 17-oct 04:17 → 19-oct 04:17 | 0 | pendiente |
| 14 | 70 | DEMO Tienda 004 | Producto DEMO 0004 | 271–273 | 17-oct 03:17 → 19-oct 03:17 | 0 | pendiente |
| 15 | 71 | DEMO Tienda 005 | Producto DEMO 0005 | 274–276 | 17-oct 02:17 → 19-oct 02:17 | 0 | descartada |
| 16 | 72 | DEMO Tienda 006 | Producto DEMO 0006 | 277–279 | 17-oct 01:17 → 19-oct 01:17 | 1 | pendiente |
| 17 | 73 | DEMO Tienda 007 | Producto DEMO 0007 | 280–282 | 17-oct 00:17 → 19-oct 00:17 | 0 | pendiente |
| 18 | 74 | DEMO Tienda 000 | Producto DEMO 0008 | 283–285 | 16-oct 23:17 → 18-oct 23:17 | 0 | pendiente |
| 19 | 75 | DEMO Tienda 001 | Producto DEMO 0009 | 286–288 | 16-oct 22:17 → 18-oct 22:17 | 0 | pendiente |
| 20 | 76 | DEMO Tienda 002 | Producto DEMO 0010 | 289–291 | 16-oct 21:17 → 18-oct 21:17 | 0 | pendiente |
| 21 | 77 | DEMO Tienda 003 | Producto DEMO 0011 | 292–294 | 16-oct 20:17 → 18-oct 20:17 | 0 | pendiente |
| 22 | 78 | DEMO Tienda 004 | Producto DEMO 0012 | 295–297 | 16-oct 19:17 → 18-oct 19:17 | 0 | pendiente |
| 23 | 79 | DEMO Tienda 005 | Producto DEMO 0013 | 298–300 | 16-oct 18:17 → 18-oct 18:17 | 0 | pendiente |
| 24 | 80 | DEMO Tienda 006 | Producto DEMO 0014 | 301–303 | 16-oct 17:17 → 18-oct 17:17 | 0 | pendiente |
| 25 | 81 | DEMO Tienda 007 | Producto DEMO 0015 | 304–306 | 16-oct 16:17 → 18-oct 16:17 | 0 | pendiente |
| 26 | 82 | DEMO Tienda 000 | Producto DEMO 0016 | 307–309 | 16-oct 15:17 → 18-oct 15:17 | 0 | pendiente |
| 27 | 83 | DEMO Tienda 001 | Producto DEMO 0017 | 310–312 | 16-oct 14:17 → 18-oct 14:17 | 0 | pendiente |
| 28 | 84 | DEMO Tienda 002 | Producto DEMO 0018 | 313–315 | 16-oct 13:17 → 18-oct 13:17 | 0 | pendiente |
| 29 | 85 | DEMO Tienda 003 | Producto DEMO 0019 | 316–318 | 16-oct 12:17 → 18-oct 12:17 | 0 | pendiente |
| 30 | 127 | DEMO Tienda 008 | Producto DEMO 0008 | 2552–2554 | 17-oct 02:10 → 19-oct 02:10 | 0 | pendiente |
| 31 | 128 | DEMO Tienda 009 | Producto DEMO 0009 | 2555–2557 | 17-oct 01:10 → 19-oct 01:10 | 0 | pendiente |
| 32 | 129 | DEMO Tienda 010 | Producto DEMO 0010 | 2558–2560 | 17-oct 00:10 → 19-oct 00:10 | 0 | pendiente |
| 33 | 130 | DEMO Tienda 011 | Producto DEMO 0011 | 2561–2563 | 16-oct 23:10 → 18-oct 23:10 | 0 | pendiente |
| 34 | 131 | DEMO Tienda 012 | Producto DEMO 0012 | 2564–2566 | 16-oct 22:10 → 18-oct 22:10 | 1 | pendiente |
| 35 | 132 | DEMO Tienda 013 | Producto DEMO 0013 | 2567–2569 | 16-oct 21:10 → 18-oct 21:10 | 0 | pendiente |
| 36 | 133 | DEMO Tienda 014 | Producto DEMO 0014 | 2570–2572 | 16-oct 20:10 → 18-oct 20:10 | 0 | pendiente |
| 37 | 134 | DEMO Tienda 015 | Producto DEMO 0015 | 2573–2575 | 16-oct 19:10 → 18-oct 19:10 | 0 | pendiente |
| 38 | 135 | DEMO Tienda 016 | Producto DEMO 0016 | 2576–2578 | 16-oct 18:10 → 18-oct 18:10 | 0 | pendiente |
| 39 | 136 | DEMO Tienda 017 | Producto DEMO 0017 | 2579–2581 | 16-oct 17:10 → 18-oct 17:10 | 0 | pendiente |
| 40 | 137 | DEMO Tienda 018 | Producto DEMO 0018 | 2582–2584 | 16-oct 16:10 → 18-oct 16:10 | 0 | pendiente |
| 41 | 138 | DEMO Tienda 019 | Producto DEMO 0019 | 2585–2587 | 16-oct 15:10 → 18-oct 15:10 | 1 | pendiente |

### Origen de los 105 repetidos

El valor procede del generador: cada escenario usa `25 + 35 + 45`. No existe un total fijo de 105 dentro del detector. El detector suma los movimientos reales y todos coinciden con la evidencia guardada.

Al ampliar small a medium, los primeros ocho pares producto-vendedor reutilizaron sus movimientos idempotentes. Los productos 0008–0019 obtuvieron ofertas adicionales de los vendedores 008–019, creando doce expedientes nuevos sin duplicar los anteriores.

### Correlación temporal y F07

Se encontraron seis pares temporales:

- Oferta 66: salidas 30, 31 y 32 de una unidad frente a reposiciones 261, 260 y 259 de 45, 35 y 25.
- Oferta 72: salida 1300 de una unidad frente a reposición 277 de 25.
- Oferta 131: salida 2061 de una unidad frente a reposición 2564 de 25.
- Oferta 138: salida 1302 de dos unidades frente a reposición 2585 de 25.

Coincidencias exactas de cantidades: **0 de 6**.

F06 solo verifica que una reposición ocurra después de una venta válida y dentro de tres días. La igualdad de cantidades pertenece a F07, que continúa como propuesta no implementada.

## 7. Duplicados y decisiones humanas

- F05: 9 expedientes y 9 huellas distintas.
- F06: 32 expedientes y 32 huellas distintas.
- Total comercial: 41 expedientes y 41 huellas distintas.
- La decisión humana de la alerta 15 (`descartada`) se conservó después del recálculo.
- El recálculo volvió a marcar su señal técnica como activa, sin sobrescribir el estado humano.

## 8. Salud y sincronización

| Componente | Resultado |
|---|---|
| MySQL | Sin líneas/pagos huérfanos, inventarios negativos ni claves de pedido duplicadas |
| MongoDB | `ping=1`, 285 productos |
| Redis | `PONG` |
| Cassandra | 2,376 líneas analíticas |
| Neo4j | 2,376 nodos Compra, 647 `BASADA_EN`, 430 `OFRECE`, 0 `COMPRO` |
| Elasticsearch | 285 documentos |
| Outbox | Sin filas pendientes, en error o fallidas en el snapshot DEMO |
| Frontend/backend/pasarela | HTTP 200 en 5175, 8005 y 8006 |

Recursos al finalizar:

- RAM disponible: 7.67 GB.
- Memoria comprometida: 57%.
- Paginación: 0 páginas/s.
- Worker automático de fraude: deshabilitado, cero procesos.
- Los seis contenedores DEMO permanecen saludables.

## 9. Recomendación para seed-full

**NO-GO inmediato para seed-full.** La integridad de medium es satisfactoria, pero quedan dos razones para detenerse:

1. El generador conserva escenarios F06 uniformes de 105 unidades; antes de full conviene aplicar la diversificación documentada sin cambiar umbrales.
2. Con 7.67 GB disponibles, full podría superar el margen conservador durante 8,000 pedidos, 12,000 líneas y la reproyección completa de Cassandra/Neo4j/Elasticsearch.

El GO debería concederse únicamente después de cerrar aplicaciones adicionales o ejecutar full por turnos con un margen de RAM mayor, aprobar la diversificación y respaldar nuevamente la DEMO medium.
