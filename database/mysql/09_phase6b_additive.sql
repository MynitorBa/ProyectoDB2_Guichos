-- =============================================================================
-- TiendaYa — Fase 6B aditiva: identidad mínima y FKs operativas nuevas
-- Conserva todas las columnas y FKs antiguas para permitir reversión.
-- =============================================================================

USE tiendaya;

CREATE TABLE IF NOT EXISTS producto_referencias (
  id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
  producto_ref   CHAR(24)     NOT NULL COMMENT 'ObjectId hexadecimal en MongoDB',
  fecha_creacion DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_producto_referencias_ref (producto_ref)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO producto_referencias (id, producto_ref, fecha_creacion)
SELECT id, producto_ref, fecha_creacion
FROM productos
WHERE producto_ref IS NOT NULL
ON DUPLICATE KEY UPDATE producto_ref = VALUES(producto_ref);

DELIMITER //
DROP PROCEDURE IF EXISTS sp_aplicar_fase6b_aditiva //
CREATE PROCEDURE sp_aplicar_fase6b_aditiva()
BEGIN
  IF EXISTS (
    SELECT 1 FROM productos WHERE producto_ref IS NULL
  ) THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Fase 6B abortada: existen productos sin producto_ref MongoDB';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'resenas'
      AND COLUMN_NAME = 'producto_referencia_id') THEN
    ALTER TABLE resenas
      ADD COLUMN producto_referencia_id INT UNSIGNED NULL AFTER producto_id;
  END IF;

  UPDATE resenas r
  JOIN producto_referencias pr ON pr.id = r.producto_id
  SET r.producto_referencia_id = pr.id
  WHERE r.producto_referencia_id IS NULL;

  IF EXISTS (SELECT 1 FROM resenas WHERE producto_referencia_id IS NULL) THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Fase 6B abortada: existen resenas sin referencia nueva';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'resenas'
      AND INDEX_NAME = 'uq_resenas_usuario_referencia') THEN
    ALTER TABLE resenas ADD UNIQUE KEY uq_resenas_usuario_referencia
      (usuario_id, producto_referencia_id);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND CONSTRAINT_NAME = 'fk_res_producto_referencia') THEN
    ALTER TABLE resenas ADD CONSTRAINT fk_res_producto_referencia
      FOREIGN KEY (producto_referencia_id)
      REFERENCES producto_referencias(id) ON DELETE RESTRICT;
  END IF;

  IF EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'resenas'
      AND COLUMN_NAME = 'producto_referencia_id' AND IS_NULLABLE = 'YES') THEN
    ALTER TABLE resenas MODIFY producto_referencia_id INT UNSIGNED NOT NULL;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'movimientos_inventario'
      AND COLUMN_NAME = 'inventario_id') THEN
    ALTER TABLE movimientos_inventario
      ADD COLUMN inventario_id INT UNSIGNED NULL AFTER producto_id;
  END IF;

  UPDATE movimientos_inventario mi
  JOIN inventario i
    ON i.producto_id = mi.producto_id AND i.bodega = 'principal'
  SET mi.inventario_id = i.id
  WHERE mi.inventario_id IS NULL;

  IF EXISTS (SELECT 1 FROM movimientos_inventario WHERE inventario_id IS NULL) THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Fase 6B abortada: existen movimientos sin inventario';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'movimientos_inventario'
      AND INDEX_NAME = 'idx_mi_inventario_id') THEN
    ALTER TABLE movimientos_inventario ADD INDEX idx_mi_inventario_id (inventario_id);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'fk_mi_inventario') THEN
    ALTER TABLE movimientos_inventario ADD CONSTRAINT fk_mi_inventario
      FOREIGN KEY (inventario_id) REFERENCES inventario(id) ON DELETE RESTRICT;
  END IF;

  IF EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'movimientos_inventario'
      AND COLUMN_NAME = 'inventario_id' AND IS_NULLABLE = 'YES') THEN
    ALTER TABLE movimientos_inventario MODIFY inventario_id INT UNSIGNED NOT NULL;
  END IF;

  -- Limpia exclusivamente la referencia intermedia introducida durante el
  -- desarrollo de 6B; no formaba parte del esquema histórico.
  IF EXISTS (SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'fk_mi_oferta') THEN
    ALTER TABLE movimientos_inventario DROP FOREIGN KEY fk_mi_oferta;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'movimientos_inventario'
      AND COLUMN_NAME = 'oferta_id') THEN
    ALTER TABLE movimientos_inventario DROP COLUMN oferta_id;
  END IF;
END //

CALL sp_aplicar_fase6b_aditiva() //
DROP PROCEDURE sp_aplicar_fase6b_aditiva //
DELIMITER ;
