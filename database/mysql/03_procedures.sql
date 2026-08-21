-- =============================================================================
-- TiendaYa — Stored Procedures
-- =============================================================================

USE tiendaya;

DELIMITER //

-- =============================================================================
-- sp_crear_pedido
-- Ejecuta el checkout completo dentro de una única transacción.
-- Parámetros de entrada:
--   p_usuario_id      INT   — usuario que compra
--   p_direccion_id    INT   — dirección de envío (debe pertenecer al usuario)
--   p_metodo_pago_id  INT   — método de pago seleccionado
--   p_items           JSON  — arreglo [{"producto_id": N, "cantidad": M}, ...]
-- Parámetros de salida:
--   p_pedido_id       INT   — id del pedido creado, NULL si falló
--   p_error           VARCHAR — descripción del error, NULL si tuvo éxito
-- =============================================================================
DROP PROCEDURE IF EXISTS sp_crear_pedido //

CREATE PROCEDURE sp_crear_pedido(
  IN  p_usuario_id     INT UNSIGNED,
  IN  p_direccion_id   INT UNSIGNED,
  IN  p_metodo_pago_id TINYINT UNSIGNED,
  IN  p_items          JSON,
  OUT p_pedido_id      INT UNSIGNED,
  OUT p_error          VARCHAR(500)
)
BEGIN
  -- Variables de trabajo
  DECLARE v_num_items    INT DEFAULT 0;
  DECLARE v_i            INT DEFAULT 0;
  DECLARE v_producto_id  INT UNSIGNED;
  DECLARE v_cantidad     INT;
  DECLARE v_precio       DECIMAL(10,2);
  DECLARE v_nombre       VARCHAR(200);
  DECLARE v_producto_ref CHAR(24);
  DECLARE v_stock        INT;
  DECLARE v_subtotal     DECIMAL(10,2) DEFAULT 0;
  DECLARE v_impuestos    DECIMAL(10,2);
  DECLARE v_total        DECIMAL(10,2);
  DECLARE v_linea_sub    DECIMAL(10,2);

  -- El HANDLER captura cualquier error SQL y hace ROLLBACK automático.
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    SET p_pedido_id = NULL;
    SET p_error = 'Error interno al procesar el pedido. Transacción revertida.';
  END;

  SET p_pedido_id = NULL;
  SET p_error     = NULL;

  -- 1. Validar que el usuario existe y está activo
  IF NOT EXISTS (
    SELECT 1 FROM usuarios WHERE id = p_usuario_id AND estado = 'activo'
  ) THEN
    SET p_error = 'Usuario no existe o está inactivo.';
    LEAVE sp_crear_pedido;
  END IF;

  -- 2. Validar que la dirección existe y pertenece al usuario
  IF NOT EXISTS (
    SELECT 1 FROM direcciones
    WHERE id = p_direccion_id AND usuario_id = p_usuario_id AND activa = 1
  ) THEN
    SET p_error = 'Dirección no válida para este usuario.';
    LEAVE sp_crear_pedido;
  END IF;

  -- 3. Validar que hay ítems
  SET v_num_items = JSON_LENGTH(p_items);
  IF v_num_items = 0 THEN
    SET p_error = 'El carrito está vacío.';
    LEAVE sp_crear_pedido;
  END IF;

  START TRANSACTION;

  -- 4. Bloquear filas de inventario (SELECT FOR UPDATE) y verificar stock
  SET v_i = 0;
  WHILE v_i < v_num_items DO
    SET v_producto_id = JSON_UNQUOTE(JSON_EXTRACT(p_items, CONCAT('$[', v_i, '].producto_id')));
    SET v_cantidad    = JSON_UNQUOTE(JSON_EXTRACT(p_items, CONCAT('$[', v_i, '].cantidad')));

    -- Bloqueo pesimista: evita sobreventa en compras concurrentes
    SELECT cantidad_disponible INTO v_stock
    FROM inventario
    WHERE producto_id = v_producto_id AND bodega = 'principal'
    FOR UPDATE;

    IF v_stock IS NULL THEN
      SET p_error = CONCAT('Producto id=', v_producto_id, ' no tiene registro de inventario.');
      ROLLBACK;
      LEAVE sp_crear_pedido;
    END IF;

    IF v_stock < v_cantidad THEN
      SET p_error = CONCAT('Stock insuficiente para producto id=', v_producto_id,
                           '. Disponible: ', v_stock, ', solicitado: ', v_cantidad);
      ROLLBACK;
      LEAVE sp_crear_pedido;
    END IF;

    SET v_i = v_i + 1;
  END WHILE;

  -- 5. Insertar el pedido (aún sin totales, los calcularemos en el loop)
  INSERT INTO pedidos (usuario_id, direccion_id, estado, subtotal, impuestos, total)
  VALUES (p_usuario_id, p_direccion_id, 'confirmado', 0, 0, 0);
  SET p_pedido_id = LAST_INSERT_ID();

  -- 6. Procesar cada línea: insertar línea, descontar inventario, registrar movimiento
  SET v_i = 0;
  SET v_subtotal = 0;

  WHILE v_i < v_num_items DO
    SET v_producto_id = JSON_UNQUOTE(JSON_EXTRACT(p_items, CONCAT('$[', v_i, '].producto_id')));
    SET v_cantidad    = JSON_UNQUOTE(JSON_EXTRACT(p_items, CONCAT('$[', v_i, '].cantidad')));

    -- Leer precio y nombre actuales del producto (se congela en la línea)
    SELECT precio, nombre, producto_ref
    INTO v_precio, v_nombre, v_producto_ref
    FROM productos
    WHERE id = v_producto_id;

    SET v_linea_sub = v_precio * v_cantidad;
    SET v_subtotal  = v_subtotal + v_linea_sub;

    -- Insertar línea con precio y nombre congelados
    INSERT INTO pedido_lineas
      (pedido_id, producto_id, producto_ref, producto_nombre, precio_unitario, cantidad, subtotal_linea)
    VALUES
      (p_pedido_id, v_producto_id, v_producto_ref, v_nombre, v_precio, v_cantidad, v_linea_sub);

    -- Descontar inventario
    UPDATE inventario
    SET cantidad_disponible = cantidad_disponible - v_cantidad
    WHERE producto_id = v_producto_id AND bodega = 'principal';

    -- Registrar movimiento de salida
    INSERT INTO movimientos_inventario (producto_id, tipo, cantidad, motivo, pedido_id, usuario_id)
    VALUES (v_producto_id, 'salida', v_cantidad, 'venta', p_pedido_id, p_usuario_id);

    SET v_i = v_i + 1;
  END WHILE;

  -- 7. Calcular impuestos (12% IVA guatemalteco) y actualizar totales del pedido
  SET v_impuestos = ROUND(v_subtotal * 0.12, 2);
  SET v_total     = v_subtotal + v_impuestos;

  UPDATE pedidos
  SET subtotal = v_subtotal, impuestos = v_impuestos, total = v_total
  WHERE id = p_pedido_id;

  -- 8. Registrar el pago
  INSERT INTO pagos (pedido_id, metodo_pago_id, monto, estado, referencia_transaccion)
  VALUES (p_pedido_id, p_metodo_pago_id, v_total, 'aprobado',
          CONCAT('TXN-', LPAD(p_pedido_id, 8, '0'), '-', UNIX_TIMESTAMP()));

  COMMIT;

END //

DELIMITER ;
