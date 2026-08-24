-- =============================================================================
-- TiendaYa — Fase 2: estructuras aditivas del modelo producto/oferta
-- No mueve ni elimina datos. Las columnas de transición se crean nullable.
-- =============================================================================

USE tiendaya;

CREATE TABLE IF NOT EXISTS ofertas (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  producto_ref CHAR(24) NOT NULL,
  vendedor_id INT UNSIGNED NOT NULL,
  sku VARCHAR(50) NOT NULL,
  precio_actual DECIMAL(12,2) NOT NULL,
  moneda CHAR(3) NOT NULL DEFAULT 'GTQ',
  estado ENUM('borrador','activa','pausada','descontinuada') NOT NULL DEFAULT 'activa',
  version INT UNSIGNED NOT NULL DEFAULT 1,
  fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_actualizacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_oferta_vendedor_sku (vendedor_id, sku),
  UNIQUE KEY uq_oferta_vendedor_producto (vendedor_id, producto_ref),
  KEY idx_oferta_producto_ref (producto_ref),
  CONSTRAINT fk_oferta_vendedor FOREIGN KEY (vendedor_id) REFERENCES vendedores(id) ON DELETE RESTRICT,
  CONSTRAINT ck_oferta_precio CHECK (precio_actual >= 0),
  CONSTRAINT ck_oferta_version CHECK (version > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS oferta_precios_historial (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  oferta_id INT UNSIGNED NOT NULL,
  precio DECIMAL(12,2) NOT NULL,
  moneda CHAR(3) NOT NULL DEFAULT 'GTQ',
  vigente_desde DATETIME(6) NOT NULL,
  vigente_hasta DATETIME(6) NULL,
  cambiado_por INT UNSIGNED NULL,
  motivo VARCHAR(200) NULL,
  fecha_registro DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  es_vigente TINYINT GENERATED ALWAYS AS (IF(vigente_hasta IS NULL, 1, NULL)) STORED,
  PRIMARY KEY (id),
  UNIQUE KEY uq_precio_vigente_oferta (oferta_id, es_vigente),
  KEY idx_precio_oferta_desde (oferta_id, vigente_desde),
  CONSTRAINT fk_oph_oferta FOREIGN KEY (oferta_id) REFERENCES ofertas(id) ON DELETE RESTRICT,
  CONSTRAINT fk_oph_usuario FOREIGN KEY (cambiado_por) REFERENCES usuarios(id) ON DELETE SET NULL,
  CONSTRAINT ck_oph_precio CHECK (precio >= 0),
  CONSTRAINT ck_oph_intervalo CHECK (vigente_hasta IS NULL OR vigente_hasta > vigente_desde)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pedido_vendedores (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  pedido_id INT UNSIGNED NOT NULL,
  vendedor_id INT UNSIGNED NOT NULL,
  estado ENUM('pendiente','confirmado','preparando','enviado','entregado','cancelado','reembolsado') NOT NULL DEFAULT 'pendiente',
  subtotal DECIMAL(12,2) NOT NULL DEFAULT 0.00,
  costo_envio DECIMAL(12,2) NOT NULL DEFAULT 0.00,
  fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_actualizacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_pv_pedido_vendedor (pedido_id, vendedor_id),
  KEY idx_pv_vendedor_estado (vendedor_id, estado),
  CONSTRAINT fk_pv_pedido FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE,
  CONSTRAINT fk_pv_vendedor FOREIGN KEY (vendedor_id) REFERENCES vendedores(id) ON DELETE RESTRICT,
  CONSTRAINT ck_pv_subtotal CHECK (subtotal >= 0),
  CONSTRAINT ck_pv_envio CHECK (costo_envio >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pedido_direcciones (
  pedido_id INT UNSIGNED NOT NULL,
  receptor_nombre VARCHAR(200) NOT NULL,
  receptor_telefono VARCHAR(20) NULL,
  pais VARCHAR(60) NOT NULL DEFAULT 'Guatemala',
  departamento VARCHAR(60) NOT NULL,
  municipio VARCHAR(60) NOT NULL,
  linea1 VARCHAR(200) NOT NULL,
  linea2 VARCHAR(200) NULL,
  codigo_postal VARCHAR(10) NULL,
  PRIMARY KEY (pedido_id),
  CONSTRAINT fk_pd_pedido FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS outbox_eventos (
  id CHAR(36) NOT NULL,
  tipo_evento VARCHAR(100) NOT NULL,
  agregado_tipo VARCHAR(60) NOT NULL,
  agregado_id VARCHAR(64) NOT NULL,
  producto_ref CHAR(24) NULL,
  payload JSON NOT NULL,
  estado ENUM('pendiente','procesando','procesado','error') NOT NULL DEFAULT 'pendiente',
  intentos SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  ultimo_error TEXT NULL,
  creado_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  procesado_en DATETIME(6) NULL,
  PRIMARY KEY (id),
  KEY idx_outbox_estado_creado (estado, creado_en),
  KEY idx_outbox_agregado (agregado_tipo, agregado_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DELIMITER //
DROP PROCEDURE IF EXISTS sp_aplicar_fase2_aditiva //
CREATE PROCEDURE sp_aplicar_fase2_aditiva()
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'inventario' AND COLUMN_NAME = 'oferta_id') THEN
    ALTER TABLE inventario ADD COLUMN oferta_id INT UNSIGNED NULL AFTER producto_id;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'inventario' AND INDEX_NAME = 'idx_inv_oferta_id') THEN
    ALTER TABLE inventario ADD INDEX idx_inv_oferta_id (oferta_id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'fk_inv_oferta') THEN
    ALTER TABLE inventario ADD CONSTRAINT fk_inv_oferta
      FOREIGN KEY (oferta_id) REFERENCES ofertas(id) ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'pedido_lineas' AND COLUMN_NAME = 'pedido_vendedor_id') THEN
    ALTER TABLE pedido_lineas ADD COLUMN pedido_vendedor_id INT UNSIGNED NULL AFTER producto_id;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'pedido_lineas' AND COLUMN_NAME = 'oferta_id') THEN
    ALTER TABLE pedido_lineas ADD COLUMN oferta_id INT UNSIGNED NULL AFTER pedido_vendedor_id;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'pedido_lineas' AND COLUMN_NAME = 'sku_snapshot') THEN
    ALTER TABLE pedido_lineas ADD COLUMN sku_snapshot VARCHAR(50) NULL AFTER producto_ref;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'pedido_lineas' AND COLUMN_NAME = 'vendedor_nombre_snapshot') THEN
    ALTER TABLE pedido_lineas ADD COLUMN vendedor_nombre_snapshot VARCHAR(150) NULL AFTER producto_nombre;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'fk_pl_pedido_vendedor') THEN
    ALTER TABLE pedido_lineas ADD CONSTRAINT fk_pl_pedido_vendedor
      FOREIGN KEY (pedido_vendedor_id) REFERENCES pedido_vendedores(id) ON DELETE SET NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'fk_pl_oferta') THEN
    ALTER TABLE pedido_lineas ADD CONSTRAINT fk_pl_oferta
      FOREIGN KEY (oferta_id) REFERENCES ofertas(id) ON DELETE RESTRICT;
  END IF;
END //

CALL sp_aplicar_fase2_aditiva() //
DROP PROCEDURE sp_aplicar_fase2_aditiva //
DELIMITER ;
