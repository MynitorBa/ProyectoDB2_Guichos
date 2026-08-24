-- =============================================================================
-- TiendaYa — Fase 4: identidad comprable por oferta en carrito
-- Mantiene producto_id para aceptar clientes anteriores durante la transición.
-- =============================================================================

USE tiendaya;

DELIMITER //
DROP PROCEDURE IF EXISTS sp_aplicar_fase4_carrito //
CREATE PROCEDURE sp_aplicar_fase4_carrito()
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'carrito_items' AND COLUMN_NAME = 'oferta_id'
  ) THEN
    ALTER TABLE carrito_items
      ADD COLUMN oferta_id INT UNSIGNED NULL AFTER producto_id;
  END IF;

  UPDATE carrito_items ci
  JOIN productos p ON p.id = ci.producto_id
  JOIN ofertas o
    ON o.producto_ref = p.producto_ref
   AND o.vendedor_id = p.vendedor_id
  SET ci.oferta_id = o.id
  WHERE ci.oferta_id IS NULL;

  IF EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'carrito_items'
      AND INDEX_NAME = 'uq_ci_carrito_producto'
  ) THEN
    ALTER TABLE carrito_items DROP INDEX uq_ci_carrito_producto;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'carrito_items'
      AND INDEX_NAME = 'idx_ci_producto'
  ) THEN
    ALTER TABLE carrito_items ADD INDEX idx_ci_producto (producto_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'carrito_items'
      AND INDEX_NAME = 'uq_ci_carrito_oferta'
  ) THEN
    ALTER TABLE carrito_items
      ADD UNIQUE KEY uq_ci_carrito_oferta (carrito_id, oferta_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'fk_ci_oferta'
  ) THEN
    ALTER TABLE carrito_items
      ADD CONSTRAINT fk_ci_oferta
      FOREIGN KEY (oferta_id) REFERENCES ofertas(id) ON DELETE RESTRICT;
  END IF;
END //

CALL sp_aplicar_fase4_carrito() //
DROP PROCEDURE sp_aplicar_fase4_carrito //
DELIMITER ;
