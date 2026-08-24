-- =============================================================================
-- TiendaYa — Fase 6B: corte físico del modelo producto/oferta
-- Requiere 09_phase6b_additive.sql y un respaldo lógico verificado.
-- =============================================================================

USE tiendaya;

DELIMITER //
DROP PROCEDURE IF EXISTS sp_aplicar_fase6b_cutover //
CREATE PROCEDURE sp_aplicar_fase6b_cutover()
BEGIN
  -- Todas las comprobaciones ocurren antes del primer ALTER/DROP.
  IF EXISTS (SELECT 1 FROM inventario WHERE oferta_id IS NULL) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT =
      'Corte 6B abortado: inventarios sin oferta';
  END IF;
  IF EXISTS (
    SELECT 1 FROM inventario
    GROUP BY oferta_id, bodega HAVING COUNT(*) > 1
  ) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT =
      'Corte 6B abortado: inventario duplicado por oferta y bodega';
  END IF;
  IF EXISTS (SELECT 1 FROM carrito_items WHERE oferta_id IS NULL) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT =
      'Corte 6B abortado: items de carrito sin oferta';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pedido_lineas
    WHERE pedido_vendedor_id IS NULL OR oferta_id IS NULL
       OR producto_ref IS NULL OR sku_snapshot IS NULL
       OR vendedor_nombre_snapshot IS NULL
  ) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT =
      'Corte 6B abortado: lineas de pedido incompletas';
  END IF;
  IF EXISTS (SELECT 1 FROM resenas WHERE producto_referencia_id IS NULL) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT =
      'Corte 6B abortado: resenas sin referencia minima';
  END IF;
  IF EXISTS (
    SELECT 1 FROM movimientos_inventario WHERE inventario_id IS NULL
  ) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT =
      'Corte 6B abortado: movimientos sin inventario';
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'productos'
  ) AND EXISTS (
    SELECT 1 FROM productos p
    LEFT JOIN producto_referencias pr
      ON pr.id = p.id AND pr.producto_ref = p.producto_ref
    WHERE pr.id IS NULL
  ) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT =
      'Corte 6B abortado: el registro minimo no cubre productos heredados';
  END IF;

  -- Carrito: la identidad comprable es exclusivamente oferta_id.
  IF EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'carrito_items'
      AND COLUMN_NAME = 'oferta_id' AND IS_NULLABLE = 'YES') THEN
    ALTER TABLE carrito_items MODIFY oferta_id INT UNSIGNED NOT NULL;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'fk_ci_producto') THEN
    ALTER TABLE carrito_items DROP FOREIGN KEY fk_ci_producto;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'carrito_items'
      AND INDEX_NAME = 'idx_ci_producto') THEN
    ALTER TABLE carrito_items DROP INDEX idx_ci_producto;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'carrito_items'
      AND COLUMN_NAME = 'producto_id') THEN
    ALTER TABLE carrito_items DROP COLUMN producto_id;
  END IF;

  -- Inventario pertenece a una oferta; movimiento apunta a la fila exacta.
  IF EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'inventario'
      AND COLUMN_NAME = 'oferta_id' AND IS_NULLABLE = 'YES') THEN
    ALTER TABLE inventario MODIFY oferta_id INT UNSIGNED NOT NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'inventario'
      AND INDEX_NAME = 'uq_inv_oferta_bodega') THEN
    ALTER TABLE inventario ADD UNIQUE KEY uq_inv_oferta_bodega (oferta_id, bodega);
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'fk_mi_producto') THEN
    ALTER TABLE movimientos_inventario DROP FOREIGN KEY fk_mi_producto;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'movimientos_inventario'
      AND INDEX_NAME = 'idx_mi_producto_id') THEN
    ALTER TABLE movimientos_inventario DROP INDEX idx_mi_producto_id;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'movimientos_inventario'
      AND COLUMN_NAME = 'producto_id') THEN
    ALTER TABLE movimientos_inventario DROP COLUMN producto_id;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'fk_inv_producto') THEN
    ALTER TABLE inventario DROP FOREIGN KEY fk_inv_producto;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'inventario'
      AND INDEX_NAME = 'uq_inv_producto_bodega') THEN
    ALTER TABLE inventario DROP INDEX uq_inv_producto_bodega;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'inventario'
      AND INDEX_NAME = 'idx_inv_producto_id') THEN
    ALTER TABLE inventario DROP INDEX idx_inv_producto_id;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'inventario'
      AND COLUMN_NAME = 'producto_id') THEN
    ALTER TABLE inventario DROP COLUMN producto_id;
  END IF;

  -- El pedido queda autosuficiente mediante oferta y snapshots históricos.
  IF EXISTS (SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'fk_pl_pedido_vendedor') THEN
    ALTER TABLE pedido_lineas DROP FOREIGN KEY fk_pl_pedido_vendedor;
  END IF;
  ALTER TABLE pedido_lineas
    MODIFY pedido_vendedor_id INT UNSIGNED NOT NULL,
    MODIFY oferta_id INT UNSIGNED NOT NULL,
    MODIFY producto_ref CHAR(24) NOT NULL,
    MODIFY sku_snapshot VARCHAR(50) NOT NULL,
    MODIFY vendedor_nombre_snapshot VARCHAR(150) NOT NULL;
  IF NOT EXISTS (SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'fk_pl_pedido_vendedor') THEN
    ALTER TABLE pedido_lineas ADD CONSTRAINT fk_pl_pedido_vendedor
      FOREIGN KEY (pedido_vendedor_id) REFERENCES pedido_vendedores(id)
      ON DELETE RESTRICT;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'fk_pl_producto') THEN
    ALTER TABLE pedido_lineas DROP FOREIGN KEY fk_pl_producto;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'pedido_lineas'
      AND INDEX_NAME = 'idx_pl_producto_id') THEN
    ALTER TABLE pedido_lineas DROP INDEX idx_pl_producto_id;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'pedido_lineas'
      AND COLUMN_NAME = 'producto_id') THEN
    ALTER TABLE pedido_lineas DROP COLUMN producto_id;
  END IF;

  -- Reseñas conservan integridad por la referencia mínima del producto.
  IF EXISTS (SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'fk_res_producto') THEN
    ALTER TABLE resenas DROP FOREIGN KEY fk_res_producto;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'resenas'
      AND INDEX_NAME = 'uq_resenas_usuario_producto') THEN
    ALTER TABLE resenas DROP INDEX uq_resenas_usuario_producto;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'resenas'
      AND INDEX_NAME = 'idx_res_producto_id') THEN
    ALTER TABLE resenas DROP INDEX idx_res_producto_id;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'resenas'
      AND COLUMN_NAME = 'producto_id') THEN
    ALTER TABLE resenas DROP COLUMN producto_id;
  END IF;

  DROP TABLE IF EXISTS producto_imagenes;
  DROP TABLE IF EXISTS productos;
END //

CALL sp_aplicar_fase6b_cutover() //
DROP PROCEDURE sp_aplicar_fase6b_cutover //
DROP PROCEDURE IF EXISTS sp_crear_pedido //
DELIMITER ;
