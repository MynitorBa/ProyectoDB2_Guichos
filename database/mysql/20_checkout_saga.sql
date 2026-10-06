-- =============================================================================
-- Migración 20 (Entrega 3): checkout como saga con pasarela de pagos externa.
--
-- El pedido se crea primero en estado 'pendiente' reservando inventario; el
-- cobro ocurre fuera de la transacción y un segundo paso confirma o compensa.
-- La clave de idempotencia evita pedidos y cargos duplicados ante reintentos.
--
-- Aditiva e idempotente: puede ejecutarse varias veces.
-- =============================================================================

-- ─── 1. Pedidos: idempotencia, vencimiento de la reserva y motivo de cancelación
SET @col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE table_schema = DATABASE() AND table_name = 'pedidos' AND column_name = 'clave_idempotencia');
SET @sql = IF(@col = 0,
  'ALTER TABLE pedidos
     ADD COLUMN clave_idempotencia CHAR(36) NULL AFTER notas,
     ADD COLUMN huella_solicitud CHAR(64) NULL AFTER clave_idempotencia,
     ADD COLUMN reserva_expira_en DATETIME NULL AFTER huella_solicitud,
     ADD COLUMN motivo_cancelacion VARCHAR(160) NULL AFTER reserva_expira_en,
     ADD UNIQUE KEY uq_pedidos_clave_idempotencia (clave_idempotencia),
     ADD KEY idx_pedidos_estado_reserva (estado, reserva_expira_en)',
  'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ─── 2. Pagos: estado en verificación y trazabilidad con la pasarela ─────────
ALTER TABLE pagos
  MODIFY estado ENUM('pendiente','en_verificacion','aprobado','rechazado','reembolsado') NOT NULL DEFAULT 'pendiente';

SET @col = (SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE table_schema = DATABASE() AND table_name = 'pagos' AND column_name = 'clave_idempotencia');
SET @sql = IF(@col = 0,
  'ALTER TABLE pagos
     ADD COLUMN clave_idempotencia CHAR(36) NULL AFTER referencia_transaccion,
     ADD COLUMN referencia_pasarela VARCHAR(64) NULL AFTER clave_idempotencia,
     ADD COLUMN intentos SMALLINT UNSIGNED NOT NULL DEFAULT 0 AFTER referencia_pasarela,
     ADD COLUMN ultimo_error TEXT NULL AFTER intentos,
     ADD COLUMN actualizado_en DATETIME NULL AFTER ultimo_error,
     ADD UNIQUE KEY uq_pagos_clave_idempotencia (clave_idempotencia),
     ADD KEY idx_pagos_estado (estado)',
  'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ─── 3. Bitácora de la saga: cada transición del checkout queda registrada ───
CREATE TABLE IF NOT EXISTS checkout_saga_pasos (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  pedido_id INT UNSIGNED NOT NULL,
  paso VARCHAR(40) NOT NULL,
  resultado VARCHAR(30) NOT NULL,
  detalle JSON NULL,
  creado_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY idx_saga_pedido (pedido_id, id),
  KEY idx_saga_creado (creado_en),
  CONSTRAINT fk_saga_pedido FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
