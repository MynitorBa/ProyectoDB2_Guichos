-- =============================================================================
-- Migración 19 (Entrega 3): outbox por destino con reintentos escalonados.
--
-- Cada evento de negocio se encola como una fila por componente de destino
-- (mongo, busqueda, cassandra, neo4j, redis). Así la caída de un componente
-- no retrasa ni bloquea la sincronización de los demás.
--
-- Aditiva e idempotente: puede ejecutarse varias veces.
-- =============================================================================

-- ─── 1. Componente de destino ────────────────────────────────────────────────
SET @col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE table_schema = DATABASE() AND table_name = 'outbox_eventos' AND column_name = 'destino'
);
SET @sql = IF(@col = 0,
    'ALTER TABLE outbox_eventos ADD COLUMN destino ENUM(''mongo'',''busqueda'',''cassandra'',''neo4j'',''redis'') NOT NULL DEFAULT ''mongo'' AFTER tipo_evento',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Los eventos analíticos existentes siempre se proyectaron hacia Cassandra.
UPDATE outbox_eventos
SET destino = 'cassandra'
WHERE tipo_evento LIKE 'analytics.%' AND destino <> 'cassandra';

-- ─── 2. Orden global de encolado ─────────────────────────────────────────────
-- El id es un UUID; secuencia da un orden total y estable para procesar.
SET @col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE table_schema = DATABASE() AND table_name = 'outbox_eventos' AND column_name = 'secuencia'
);
SET @sql = IF(@col = 0,
    'ALTER TABLE outbox_eventos ADD COLUMN secuencia BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, ADD UNIQUE KEY uq_outbox_secuencia (secuencia)',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ─── 3. Próximo intento (backoff exponencial) ────────────────────────────────
SET @col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE table_schema = DATABASE() AND table_name = 'outbox_eventos' AND column_name = 'siguiente_intento_en'
);
SET @sql = IF(@col = 0,
    'ALTER TABLE outbox_eventos ADD COLUMN siguiente_intento_en DATETIME(6) NULL AFTER procesado_en',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ─── 4. Estado terminal para eventos que agotaron sus reintentos ─────────────
ALTER TABLE outbox_eventos
  MODIFY estado ENUM('pendiente','procesando','procesado','error','fallido') NOT NULL DEFAULT 'pendiente';

-- ─── 5. Índices para reclamar eventos y resumir por destino ──────────────────
SET @cnt = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE table_schema = DATABASE() AND table_name = 'outbox_eventos' AND index_name = 'idx_outbox_reclamo'
);
SET @sql = IF(@cnt = 0,
    'ALTER TABLE outbox_eventos ADD INDEX idx_outbox_reclamo (estado, siguiente_intento_en, secuencia)',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @cnt = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE table_schema = DATABASE() AND table_name = 'outbox_eventos' AND index_name = 'idx_outbox_destino_estado'
);
SET @sql = IF(@cnt = 0,
    'ALTER TABLE outbox_eventos ADD INDEX idx_outbox_destino_estado (destino, estado)',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
