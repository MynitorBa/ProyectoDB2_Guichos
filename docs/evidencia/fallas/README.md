# Pruebas de falla del checkout distribuido — resumen

Actualizado el 2026-10-30 19:48 con `backend/scripts/demo_fallas.py` contra el sistema en ejecución (API, pasarela simulada y contenedores Docker reales). Cada escenario tiene la hora exacta de su corrida en su propio archivo.

E00–E17 provocan la falla deteniendo contenedores o con la pasarela; C01–C12 son los casos específicos del laboratorio, que hacen fallar un motor en un instante exacto.

| Escenario | Falla | Resultado | Métrica clave |
|---|---|---|---|
| [E00 · Compra normal y ventana de consistencia eventual](E00.md) | Ninguna (línea base) | ✅ | Respuesta del checkout: 0.28 s |
| [E01 · La pasarela rechaza el pago](E01.md) | Pago rechazado (fondos insuficientes) | ✅ | — |
| [E02 · La pasarela cobra y responde error 500](E02.md) | Cargo realizado pero respuesta 500: el cliente no sabe si se cobró | ✅ | Intentos contra la pasarela: 2 |
| [E03 · La pasarela cobra pero no responde a tiempo](E03.md) | Timeout en todos los intentos con el cargo ya realizado | ✅ | Respuesta al cliente (202): 10.22 s |
| [E04 · La pasarela responde 503 sin cobrar](E04.md) | Error 503 en todos los intentos; el cargo nunca ocurrió | ✅ | Compensación por el reconciliador: 23.7 s |
| [E05 · Caída entre la reserva y el cobro](E05.md) | El proceso cae en el punto «checkout.despues_reserva» | ✅ | Resolución por el recolector: 63.9 s |
| [E06 · Caída después de cobrar y antes de confirmar](E06.md) | El proceso cae en el punto «checkout.despues_cobro» | ✅ | Resolución por el recolector: 63.9 s |
| [E07 · Falla la transacción de confirmación](E07.md) | El proceso cae en el punto «checkout.confirmacion» | ✅ | Resolución por el recolector: 63.9 s |
| [E08 · Doble envío de la misma compra](E08.md) | Dos solicitudes simultáneas con la misma clave (doble clic o reintento del navegador) | ✅ | — |
| [E09 · Redis caído durante el checkout (plan B)](E09.md) | El carrito (Redis) no responde | ✅ | Respuesta del checkout sin Redis: 0.33 s |
| [E10 · MongoDB caído durante una compra](E10.md) | MongoDB detenido (`docker stop tiendaya_mongo`) | ✅ | Demás destinos al día, con el componente aún caído: 4.5 s |
| [E11 · Elasticsearch caído durante una compra](E11.md) | Elasticsearch detenido (`docker stop tiendaya_elasticsearch`) | ✅ | Demás destinos al día, con el componente aún caído: 0.0 s |
| [E12 · Neo4j caído durante una compra](E12.md) | Neo4j detenido (`docker stop tiendaya_neo4j`) | ✅ | Demás destinos al día, con el componente aún caído: 2.0 s |
| [E13 · Cassandra caído durante una compra](E13.md) | Cassandra detenido (`docker stop tiendaya_cassandra`) | ✅ | Demás destinos al día, con el componente aún caído: 1.0 s |
| [E14 · Catálogo con MongoDB caído (plan B)](E14.md) | MongoDB detenido | ✅ | Primera petición sin MongoDB: 3.27 s |
| [E15 · Búsqueda con Elasticsearch y MongoDB caídos (plan B)](E15.md) | Elasticsearch y MongoDB detenidos | ✅ | — |
| [E16 · Recomendaciones y fraude con Neo4j caído (plan B)](E16.md) | Neo4j detenido | ✅ | — |
| [E17 · Pedido en cola con MySQL caído (plan B)](E17.md) | MySQL detenido | ✅ | Procesada tras volver MySQL: 12.1 s |
| [C01 · ¿Qué pasa si Redis se cae justo cuando presiono «Comprar»?](C01.md) | Redis · Al presionar Comprar | ✅ | Respuesta del checkout sin Redis en ese instante: 0.25 s |
| [C02 · ¿Qué pasa si MySQL deja de responder justo al recibir mi compra?](C02.md) | MySQL · Al presionar Comprar | ✅ | Procesada por la cola tras volver MySQL: 17.1 s |
| [C03 · ¿Qué pasa si MySQL se cae a mitad de la reserva, con el inventario bloqueado?](C03.md) | MySQL · Durante la reserva (T1) | ✅ | Procesada por la cola tras volver MySQL: 13.1 s |
| [C04 · ¿Qué pasa si otra compra bloquea las mismas filas en el mismo instante (deadlock)?](C04.md) | MySQL · Durante la reserva (T1) | ✅ | — |
| [C05 · ¿Qué pasa si se pierde la respuesta justo después de pagar y vuelvo a presionar «Comprar»?](C05.md) | Red / navegador · Después de cobrar | ✅ | — |
| [C06 · ¿Qué pasa si Redis se cae justo al vaciar el carrito, con la venta ya confirmada?](C06.md) | Redis · Después de confirmar | ✅ | Limpieza del carrito por el outbox: 1.0 s |
| [C07 · ¿Qué pasa si Redis se cae justo al cerrar mi reserva flash, con la venta ya hecha?](C07.md) | Redis · Después de confirmar | ✅ | Reserva cerrada en Redis por el outbox: 0.5 s |
| [C08 · ¿Qué pasa si Redis se cae justo al validar mi reserva flash al comprar?](C08.md) | Redis · Al presionar Comprar | ✅ | — |
| [C09 · ¿Qué pasa si MongoDB se cae justo al armar las líneas del pedido?](C09.md) | MongoDB · Durante la reserva (T1) | ✅ | — |
| [C10 · ¿Qué pasa si Redis se cae justo al agregar un producto al carrito?](C10.md) | Redis · Al agregar al carrito | ✅ | — |
| [C11 · ¿Qué pasa si Redis aparta mi unidad flash pero se cae antes de responder?](C11.md) | Redis · Al reservar una oferta flash | ✅ | — |
| [C12 · ¿Qué pasa si el servicio de embeddings se cae justo cuando busco?](C12.md) | Embeddings · Al buscar | ✅ | Búsqueda sin el servicio de embeddings: 0.2 s |
