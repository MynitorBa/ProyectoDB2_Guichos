-- =============================================================================
-- TiendaYa — Fase 3: backfill reproducible del modelo producto/oferta
-- Conserva las columnas y tablas antiguas. Todos los cambios DML son atómicos.
-- =============================================================================

USE tiendaya;

DELIMITER //
DROP PROCEDURE IF EXISTS sp_aplicar_fase3_backfill //
CREATE PROCEDURE sp_aplicar_fase3_backfill()
BEGIN
  DECLARE filas_invalidas INT DEFAULT 0;

  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;

  -- Precondiciones: el backfill no debe inventar relaciones ausentes.
  SELECT COUNT(*) INTO filas_invalidas
  FROM productos
  WHERE producto_ref IS NULL
     OR producto_ref NOT REGEXP '^[0-9a-fA-F]{24}$';
  IF filas_invalidas > 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Fase 3 abortada: hay productos sin producto_ref MongoDB valido';
  END IF;

  SELECT COUNT(*) INTO filas_invalidas
  FROM pedido_lineas pl
  LEFT JOIN productos p ON p.id = pl.producto_id
  LEFT JOIN vendedores v ON v.id = p.vendedor_id
  WHERE p.id IS NULL OR v.id IS NULL;
  IF filas_invalidas > 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Fase 3 abortada: hay lineas sin producto o vendedor recuperable';
  END IF;

  SELECT COUNT(*) INTO filas_invalidas
  FROM pedidos pe
  LEFT JOIN direcciones d ON d.id = pe.direccion_id
  LEFT JOIN usuarios u ON u.id = pe.usuario_id
  WHERE d.id IS NULL OR u.id IS NULL;
  IF filas_invalidas > 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Fase 3 abortada: hay pedidos sin direccion o usuario recuperable';
  END IF;

  START TRANSACTION;

  INSERT INTO ofertas (
    producto_ref, vendedor_id, sku, precio_actual, moneda, estado,
    version, fecha_creacion, fecha_actualizacion
  )
  SELECT
    p.producto_ref,
    p.vendedor_id,
    p.sku,
    p.precio,
    'GTQ',
    CASE p.estado
      WHEN 'activo' THEN 'activa'
      WHEN 'inactivo' THEN 'pausada'
      WHEN 'borrador' THEN 'borrador'
      ELSE 'descontinuada'
    END,
    1,
    p.fecha_creacion,
    p.fecha_actualizacion
  FROM productos p
  LEFT JOIN ofertas o
    ON o.vendedor_id = p.vendedor_id
   AND o.producto_ref = p.producto_ref
  WHERE o.id IS NULL;

  INSERT INTO oferta_precios_historial (
    oferta_id, precio, moneda, vigente_desde, vigente_hasta,
    cambiado_por, motivo
  )
  SELECT
    o.id,
    o.precio_actual,
    o.moneda,
    o.fecha_creacion,
    NULL,
    NULL,
    'Precio inicial importado durante Fase 3'
  FROM ofertas o
  WHERE NOT EXISTS (
    SELECT 1
    FROM oferta_precios_historial h
    WHERE h.oferta_id = o.id
  );

  UPDATE inventario i
  JOIN productos p ON p.id = i.producto_id
  JOIN ofertas o
    ON o.vendedor_id = p.vendedor_id
   AND o.producto_ref = p.producto_ref
  SET i.oferta_id = o.id
  WHERE i.oferta_id IS NULL;

  INSERT INTO pedido_vendedores (
    pedido_id, vendedor_id, estado, subtotal, costo_envio,
    fecha_creacion, fecha_actualizacion
  )
  SELECT
    pl.pedido_id,
    p.vendedor_id,
    CASE pe.estado
      WHEN 'pendiente' THEN 'pendiente'
      WHEN 'confirmado' THEN 'confirmado'
      WHEN 'enviado' THEN 'enviado'
      WHEN 'entregado' THEN 'entregado'
      WHEN 'cancelado' THEN 'cancelado'
      ELSE 'reembolsado'
    END,
    SUM(pl.subtotal_linea),
    0.00,
    pe.fecha_creacion,
    pe.fecha_actualizacion
  FROM pedido_lineas pl
  JOIN productos p ON p.id = pl.producto_id
  JOIN pedidos pe ON pe.id = pl.pedido_id
  LEFT JOIN pedido_vendedores pv
    ON pv.pedido_id = pl.pedido_id
   AND pv.vendedor_id = p.vendedor_id
  WHERE pv.id IS NULL
  GROUP BY
    pl.pedido_id, p.vendedor_id, pe.estado,
    pe.fecha_creacion, pe.fecha_actualizacion;

  INSERT INTO pedido_direcciones (
    pedido_id, receptor_nombre, receptor_telefono, pais,
    departamento, municipio, linea1, linea2, codigo_postal
  )
  SELECT
    pe.id,
    TRIM(CONCAT_WS(' ', u.nombre, u.apellido)),
    u.telefono,
    d.pais,
    d.departamento,
    d.municipio,
    d.linea1,
    d.linea2,
    d.codigo_postal
  FROM pedidos pe
  JOIN direcciones d ON d.id = pe.direccion_id
  JOIN usuarios u ON u.id = pe.usuario_id
  LEFT JOIN pedido_direcciones pd ON pd.pedido_id = pe.id
  WHERE pd.pedido_id IS NULL;

  UPDATE pedido_lineas pl
  JOIN productos p ON p.id = pl.producto_id
  JOIN vendedores v ON v.id = p.vendedor_id
  JOIN ofertas o
    ON o.vendedor_id = p.vendedor_id
   AND o.producto_ref = p.producto_ref
  JOIN pedido_vendedores pv
    ON pv.pedido_id = pl.pedido_id
   AND pv.vendedor_id = p.vendedor_id
  SET
    pl.pedido_vendedor_id = COALESCE(pl.pedido_vendedor_id, pv.id),
    pl.oferta_id = COALESCE(pl.oferta_id, o.id),
    pl.producto_ref = COALESCE(pl.producto_ref, p.producto_ref),
    pl.sku_snapshot = COALESCE(pl.sku_snapshot, p.sku),
    pl.vendedor_nombre_snapshot = COALESCE(
      pl.vendedor_nombre_snapshot,
      v.nombre_comercial
    )
  WHERE pl.pedido_vendedor_id IS NULL
     OR pl.oferta_id IS NULL
     OR pl.producto_ref IS NULL
     OR pl.sku_snapshot IS NULL
     OR pl.vendedor_nombre_snapshot IS NULL;

  -- Poscondiciones: cualquier cobertura incompleta revierte la transacción.
  SELECT COUNT(*) INTO filas_invalidas
  FROM productos p
  LEFT JOIN ofertas o
    ON o.vendedor_id = p.vendedor_id
   AND o.producto_ref = p.producto_ref
  WHERE o.id IS NULL;
  IF filas_invalidas > 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Fase 3 revertida: quedaron productos sin oferta';
  END IF;

  SELECT COUNT(*) INTO filas_invalidas
  FROM inventario
  WHERE oferta_id IS NULL;
  IF filas_invalidas > 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Fase 3 revertida: quedaron inventarios sin oferta';
  END IF;

  SELECT COUNT(*) INTO filas_invalidas
  FROM ofertas o
  LEFT JOIN oferta_precios_historial h
    ON h.oferta_id = o.id AND h.vigente_hasta IS NULL
  WHERE h.id IS NULL;
  IF filas_invalidas > 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Fase 3 revertida: quedaron ofertas sin precio vigente';
  END IF;

  SELECT COUNT(*) INTO filas_invalidas
  FROM pedido_lineas
  WHERE pedido_vendedor_id IS NULL
     OR oferta_id IS NULL
     OR producto_ref IS NULL
     OR sku_snapshot IS NULL
     OR vendedor_nombre_snapshot IS NULL;
  IF filas_invalidas > 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Fase 3 revertida: quedaron lineas sin enlaces o snapshots';
  END IF;

  SELECT COUNT(*) INTO filas_invalidas
  FROM pedidos pe
  LEFT JOIN pedido_direcciones pd ON pd.pedido_id = pe.id
  WHERE pd.pedido_id IS NULL;
  IF filas_invalidas > 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Fase 3 revertida: quedaron pedidos sin snapshot de direccion';
  END IF;

  COMMIT;
END //

CALL sp_aplicar_fase3_backfill() //
DROP PROCEDURE sp_aplicar_fase3_backfill //
DELIMITER ;
