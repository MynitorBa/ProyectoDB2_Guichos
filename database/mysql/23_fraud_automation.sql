-- =============================================================================
-- Migración 23: vigencia de alertas y bitácora del análisis de fraude.
-- Aditiva e idempotente. No cambia estados ni elimina expedientes existentes.
-- =============================================================================

CREATE TABLE IF NOT EXISTS fraud_analysis_runs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  origen ENUM('manual','automatico') NOT NULL,
  estado ENUM('en_curso','exitosa','fallida') NOT NULL DEFAULT 'en_curso',
  iniciada_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  finalizada_en DATETIME(6) NULL,
  duracion_ms INT UNSIGNED NULL,
  resumen JSON NULL,
  error TEXT NULL,
  ejecutor VARCHAR(160) NULL,
  PRIMARY KEY (id),
  KEY idx_fraud_runs_origen_fecha (origen, iniciada_en),
  KEY idx_fraud_runs_estado_fecha (estado, iniciada_en)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DELIMITER //
DROP PROCEDURE IF EXISTS sp_migrar_automatizacion_fraude //
CREATE PROCEDURE sp_migrar_automatizacion_fraude()
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='alertas_fraude'
      AND COLUMN_NAME='activa'
  ) THEN
    ALTER TABLE alertas_fraude
      ADD COLUMN activa TINYINT(1) NOT NULL DEFAULT 1 AFTER estado;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='alertas_fraude'
      AND COLUMN_NAME='resuelta_en'
  ) THEN
    ALTER TABLE alertas_fraude
      ADD COLUMN resuelta_en DATETIME(6) NULL AFTER ultima_deteccion;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='alertas_fraude'
      AND COLUMN_NAME='ultima_ejecucion_id'
  ) THEN
    ALTER TABLE alertas_fraude
      ADD COLUMN ultima_ejecucion_id BIGINT UNSIGNED NULL AFTER resuelta_en;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='alertas_fraude'
      AND COLUMN_NAME='origen_ultima_deteccion'
  ) THEN
    ALTER TABLE alertas_fraude
      ADD COLUMN origen_ultima_deteccion ENUM('manual','automatico') NULL
      AFTER ultima_ejecucion_id;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='alertas_fraude'
      AND INDEX_NAME='idx_alerta_vigencia'
  ) THEN
    ALTER TABLE alertas_fraude
      ADD KEY idx_alerta_vigencia (activa, tipo, ultima_deteccion);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA=DATABASE()
      AND CONSTRAINT_NAME='fk_alerta_ultima_ejecucion'
  ) THEN
    ALTER TABLE alertas_fraude
      ADD CONSTRAINT fk_alerta_ultima_ejecucion
      FOREIGN KEY (ultima_ejecucion_id) REFERENCES fraud_analysis_runs(id)
      ON DELETE SET NULL;
  END IF;
END //
CALL sp_migrar_automatizacion_fraude() //
DROP PROCEDURE sp_migrar_automatizacion_fraude //
DELIMITER ;
