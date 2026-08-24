-- =============================================================================
-- TiendaYa — Fase 7: integridad producto/categoría/oferta
-- El ejecutor Python llena categoria_id desde MongoDB antes de imponer FKs.
-- =============================================================================

USE tiendaya;

DELIMITER //
DROP PROCEDURE IF EXISTS sp_aplicar_fase7_integridad_referencias //
CREATE PROCEDURE sp_aplicar_fase7_integridad_referencias()
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'producto_referencias'
      AND COLUMN_NAME = 'categoria_id') THEN
    ALTER TABLE producto_referencias
      ADD COLUMN categoria_id INT UNSIGNED NULL AFTER producto_ref;
  END IF;

  IF EXISTS (
    SELECT 1 FROM producto_referencias WHERE categoria_id IS NULL
  ) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT =
      'Fase 7 abortada: referencias de producto sin categoria';
  END IF;

  IF EXISTS (
    SELECT 1 FROM producto_referencias pr
    LEFT JOIN categorias c ON c.id = pr.categoria_id
    WHERE c.id IS NULL
  ) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT =
      'Fase 7 abortada: categoria_id invalida';
  END IF;

  IF EXISTS (
    SELECT 1 FROM ofertas o
    LEFT JOIN producto_referencias pr ON pr.producto_ref = o.producto_ref
    WHERE pr.id IS NULL
  ) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT =
      'Fase 7 abortada: ofertas sin referencia de producto';
  END IF;

  IF EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'producto_referencias'
      AND COLUMN_NAME = 'categoria_id' AND IS_NULLABLE = 'YES') THEN
    ALTER TABLE producto_referencias
      MODIFY categoria_id INT UNSIGNED NOT NULL;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'producto_referencias'
      AND INDEX_NAME = 'idx_pr_categoria') THEN
    ALTER TABLE producto_referencias
      ADD INDEX idx_pr_categoria (categoria_id);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND CONSTRAINT_NAME = 'fk_pr_categoria') THEN
    ALTER TABLE producto_referencias
      ADD CONSTRAINT fk_pr_categoria
      FOREIGN KEY (categoria_id) REFERENCES categorias(id) ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND CONSTRAINT_NAME = 'fk_oferta_producto_referencia') THEN
    ALTER TABLE ofertas
      ADD CONSTRAINT fk_oferta_producto_referencia
      FOREIGN KEY (producto_ref) REFERENCES producto_referencias(producto_ref)
      ON DELETE RESTRICT;
  END IF;
END //

CALL sp_aplicar_fase7_integridad_referencias() //
DROP PROCEDURE sp_aplicar_fase7_integridad_referencias //
DELIMITER ;
