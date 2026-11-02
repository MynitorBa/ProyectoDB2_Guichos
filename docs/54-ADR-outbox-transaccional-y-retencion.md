# ADR — conservar el Outbox transaccional en MySQL

Estado: aceptada la ubicación del Outbox; retención pendiente de medición.

## Contexto y decisión

Pedidos, pagos, inventario y el evento derivado deben confirmarse juntos. El
Outbox se escribe en la misma transacción MySQL que la operación comercial,
con una fila por destino. Continúan la reclamación con `SKIP LOCKED`, workers
independientes, reintentos con backoff, idempotencia y estados visibles en el
panel administrativo.

Se evaluó mover el único evento a Redis Streams. Eso separaría el commit de
MySQL de la publicación: MySQL podría confirmar una compra y fallar el paso de
Redis. Una doble escritura con reconciliación añadiría complejidad sin mejorar
la garantía principal. Redis sigue siendo apropiado para carritos y reservas,
pero no reemplaza el registro transaccional. También se consideró limpiar
eventos inmediatamente al procesarlos; se descarta porque perjudica auditoría,
diagnóstico y reconstrucción.

## Retención propuesta, todavía sin borrados

El umbral de **90 días** se conserva como parámetro evaluable para el
`dry-run`; no es una política definitiva ni un programador activado.

Medir por destino y estado: conteo, edad, eventos procesados por día, tamaño de
datos e índices, latencia del reclamo, ritmo de trabajo y dependencias de
reconstrucción. Considerar un mínimo configurable de retención, inicialmente
mayor para eventos que alimentan historial o pueden reproyectarse. Ninguna
política debe tocar pendientes, procesando, error o fallidos.

El procedimiento futuro será por lotes pequeños de filas `procesado`, con
`procesado_en` anterior al umbral, límite y pausa entre lotes. Antes de
habilitarlo se exige simulación (`dry-run`), copia aislada de datos, medición
antes/después e inventario de dependencias. Borrar filas InnoDB libera espacio
reutilizable internamente; no implica una reducción inmediata del archivo en
disco. Una eventual reorganización física sería otra operación con su propia
evaluación de bloqueos y respaldo.

No se creó un job de borrado ni se eliminó ningún evento en esta fase.

En la instalación PRINCIPAL auditada el 1 de noviembre de 2026 había 48
eventos, todos `procesado`, en un solo destino histórico (`mongo`). El tamaño
aproximado reportado por InnoDB fue 16 KiB de datos y 80 KiB de índices.
Con un umbral orientativo de 90 días, la simulación encontró **cero** candidatos.
Ese tamaño no justifica una limpieza operativa inmediata. La medición en una
copia aislada y la clasificación de dependencias quedan pendientes antes de
habilitar borrados.
