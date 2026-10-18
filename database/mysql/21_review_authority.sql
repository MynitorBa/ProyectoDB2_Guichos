DELIMITER //
-- =============================================================================
-- TiendaYa — Migración 21: MySQL como autoridad durable de reseñas
-- Aditiva e idempotente. No elimina columnas ni registros heredados.
-- =============================================================================

DROP PROCEDURE IF EXISTS sp_migrar_autoridad_resenas //
CREATE PROCEDURE sp_migrar_autoridad_resenas()
BEGIN
  DECLARE v_estado_agregado BOOLEAN DEFAULT FALSE;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'resenas'
      AND COLUMN_NAME = 'public_id'
  ) THEN
    ALTER TABLE resenas ADD COLUMN public_id VARCHAR(64) NULL AFTER id;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'resenas'
      AND COLUMN_NAME = 'vendedor_id'
  ) THEN
    ALTER TABLE resenas ADD COLUMN vendedor_id INT UNSIGNED NULL AFTER producto_referencia_id;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'resenas'
      AND COLUMN_NAME = 'pedido_linea_id'
  ) THEN
    ALTER TABLE resenas ADD COLUMN pedido_linea_id INT UNSIGNED NULL AFTER vendedor_id;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'resenas'
      AND COLUMN_NAME = 'estado_moderacion'
  ) THEN
    ALTER TABLE resenas ADD COLUMN estado_moderacion
      ENUM('pendiente','aprobada','rechazada') NOT NULL DEFAULT 'pendiente'
      AFTER comentario;
    SET v_estado_agregado = TRUE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'resenas'
      AND COLUMN_NAME = 'verificada_compra'
  ) THEN
    ALTER TABLE resenas ADD COLUMN verificada_compra TINYINT(1) NOT NULL DEFAULT 0
      AFTER estado_moderacion;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'resenas'
      AND COLUMN_NAME = 'motivo_no_verificada'
  ) THEN
    ALTER TABLE resenas ADD COLUMN motivo_no_verificada VARCHAR(160) NULL
      AFTER verificada_compra;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'resenas'
      AND COLUMN_NAME = 'version'
  ) THEN
    ALTER TABLE resenas ADD COLUMN version INT UNSIGNED NOT NULL DEFAULT 1
      AFTER motivo_no_verificada;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'resenas'
      AND COLUMN_NAME = 'fecha_actualizacion'
  ) THEN
    ALTER TABLE resenas ADD COLUMN fecha_actualizacion DATETIME NOT NULL
      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER fecha;
  END IF;

  UPDATE resenas
  SET public_id = CONCAT('mysql:', id)
  WHERE public_id IS NULL OR public_id = '';

  IF v_estado_agregado THEN
    UPDATE resenas
    SET estado_moderacion = IF(aprobada = 1, 'aprobada', 'pendiente');
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'resenas'
      AND INDEX_NAME = 'uq_resenas_public_id'
  ) THEN
    ALTER TABLE resenas ADD UNIQUE KEY uq_resenas_public_id (public_id);
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'resenas'
      AND INDEX_NAME = 'uq_resenas_usuario_referencia'
  ) THEN
    ALTER TABLE resenas DROP INDEX uq_resenas_usuario_referencia;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'resenas'
      AND INDEX_NAME = 'uq_resenas_usuario_producto_vendedor'
  ) THEN
    ALTER TABLE resenas ADD UNIQUE KEY uq_resenas_usuario_producto_vendedor
      (usuario_id, producto_referencia_id, vendedor_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'fk_res_vendedor'
  ) THEN
    ALTER TABLE resenas ADD CONSTRAINT fk_res_vendedor
      FOREIGN KEY (vendedor_id) REFERENCES vendedores(id) ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'fk_res_pedido_linea'
  ) THEN
    ALTER TABLE resenas ADD CONSTRAINT fk_res_pedido_linea
      FOREIGN KEY (pedido_linea_id) REFERENCES pedido_lineas(id) ON DELETE RESTRICT;
  END IF;

  ALTER TABLE resenas MODIFY public_id VARCHAR(64) NOT NULL;
END //
CALL sp_migrar_autoridad_resenas() //
DROP PROCEDURE sp_migrar_autoridad_resenas //
DELIMITER ;

CREATE TABLE IF NOT EXISTS resena_imagenes (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  resena_id INT UNSIGNED NOT NULL,
  url VARCHAR(500) NOT NULL,
  orden SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_resena_imagen_url (resena_id, url),
  CONSTRAINT fk_resena_imagen_resena FOREIGN KEY (resena_id)
    REFERENCES resenas(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS resena_respuestas (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  public_id VARCHAR(64) NOT NULL,
  resena_id INT UNSIGNED NOT NULL,
  usuario_id INT UNSIGNED NOT NULL,
  vendedor_id INT UNSIGNED NOT NULL,
  texto TEXT NOT NULL,
  fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_actualizacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  activa TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (id),
  UNIQUE KEY uq_resena_respuesta_public_id (public_id),
  KEY idx_respuesta_resena_fecha (resena_id, fecha_creacion),
  CONSTRAINT fk_respuesta_resena FOREIGN KEY (resena_id)
    REFERENCES resenas(id) ON DELETE CASCADE,
  CONSTRAINT fk_respuesta_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuarios(id) ON DELETE RESTRICT,
  CONSTRAINT fk_respuesta_vendedor FOREIGN KEY (vendedor_id)
    REFERENCES vendedores(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
