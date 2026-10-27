# Pruebas de falla del checkout distribuido — resumen

Actualizado el 2026-10-27 11:39 con `backend/scripts/demo_fallas.py` contra el sistema en ejecución (API, pasarela simulada y contenedores Docker reales). Cada escenario tiene la hora exacta de su corrida en su propio archivo.

| Escenario | Falla | Resultado | Métrica clave |
|---|---|---|---|
| [E00 · Compra normal y ventana de consistencia eventual](E00.md) | Ninguna (línea base) | ✅ | Respuesta del checkout: 0.59 s |
| [E01 · La pasarela rechaza el pago](E01.md) | Pago rechazado (fondos insuficientes) | ✅ | — |
| [E02 · La pasarela cobra y responde error 500](E02.md) | Cargo realizado pero respuesta 500: el cliente no sabe si se cobró | ✅ | Intentos contra la pasarela: 2 |
| [E03 · La pasarela cobra pero no responde a tiempo](E03.md) | Timeout en todos los intentos con el cargo ya realizado | ✅ | Respuesta al cliente (202): 10.66 s |
| [E04 · La pasarela responde 503 sin cobrar](E04.md) | Error 503 en todos los intentos; el cargo nunca ocurrió | ✅ | Compensación por el reconciliador: 23.2 s |
| [E05 · Caída entre la reserva y el cobro](E05.md) | El proceso cae en el punto «checkout.despues_reserva» | ✅ | Resolución por el recolector: 64.0 s |
| [E06 · Caída después de cobrar y antes de confirmar](E06.md) | El proceso cae en el punto «checkout.despues_cobro» | ✅ | Resolución por el recolector: 63.4 s |
| [E07 · Falla la transacción de confirmación](E07.md) | El proceso cae en el punto «checkout.confirmacion» | ✅ | Resolución por el recolector: 63.4 s |
| [E08 · Doble envío de la misma compra](E08.md) | Dos solicitudes simultáneas con la misma clave (doble clic o reintento del navegador) | ✅ | — |
| [E09 · Redis caído durante el checkout (plan B)](E09.md) | El carrito (Redis) no responde | ✅ | Respuesta del checkout sin Redis: 0.39 s |
| [E10 · MongoDB caído durante una compra](E10.md) | MongoDB detenido (`docker stop tiendaya_mongo`) | ✅ | Demás destinos al día, con el componente aún caído: 6.5 s |
| [E11 · Elasticsearch caído durante una compra](E11.md) | Elasticsearch detenido (`docker stop tiendaya_elasticsearch`) | ✅ | Demás destinos al día, con el componente aún caído: 0.5 s |
| [E12 · Neo4j caído durante una compra](E12.md) | Neo4j detenido (`docker stop tiendaya_neo4j`) | ✅ | Demás destinos al día, con el componente aún caído: 9.1 s |
| [E13 · Cassandra caído durante una compra](E13.md) | Cassandra detenido (`docker stop tiendaya_cassandra`) | ✅ | Demás destinos al día, con el componente aún caído: 0.5 s |
| [E14 · Catálogo con MongoDB caído (plan B)](E14.md) | MongoDB detenido | ✅ | Primera petición sin MongoDB: 3.3 s |
| [E15 · Búsqueda con Elasticsearch y MongoDB caídos (plan B)](E15.md) | Elasticsearch y MongoDB detenidos | ✅ | — |
| [E16 · Recomendaciones y fraude con Neo4j caído (plan B)](E16.md) | Neo4j detenido | ✅ | — |
| [E17 · Pedido en cola con MySQL caído (plan B)](E17.md) | MySQL detenido | ✅ | Procesada tras volver MySQL: 6.1 s |
