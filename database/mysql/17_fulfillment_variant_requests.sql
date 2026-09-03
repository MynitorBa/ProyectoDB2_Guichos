-- Envíos parciales y propuesta de variante con oferta inicial. No borra datos.
ALTER TABLE pedidos MODIFY estado ENUM('pendiente','confirmado','preparando','enviado_parcial','enviado','entregado_parcial','entregado','cancelado','reembolsado') NOT NULL DEFAULT 'pendiente';
ALTER TABLE pedido_vendedores MODIFY estado ENUM('pendiente','confirmado','preparando','enviado_parcial','enviado','entregado_parcial','entregado','cancelado','reembolsado') NOT NULL DEFAULT 'pendiente';
ALTER TABLE solicitudes_catalogo MODIFY tipo ENUM('producto_nuevo','oferta_existente','variante_nueva') NOT NULL;
SET @has_check = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=DATABASE() AND TABLE_NAME='solicitudes_catalogo' AND CONSTRAINT_NAME='ck_sc_tipo_datos');
SET @ddl = IF(@has_check > 0, 'ALTER TABLE solicitudes_catalogo DROP CHECK ck_sc_tipo_datos', 'SELECT 1');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
ALTER TABLE solicitudes_catalogo ADD CONSTRAINT ck_sc_tipo_datos CHECK ((tipo='producto_nuevo' AND producto_ref_solicitado IS NULL AND nombre IS NOT NULL) OR (tipo IN ('oferta_existente','variante_nueva') AND producto_ref_solicitado IS NOT NULL AND nombre IS NULL));
CREATE TABLE IF NOT EXISTS pedido_envios (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  pedido_vendedor_id INT UNSIGNED NOT NULL,
  estado ENUM('enviado','entregado') NOT NULL DEFAULT 'enviado',
  referencia VARCHAR(120) NULL,
  creado_por INT UNSIGNED NULL,
  entregado_por INT UNSIGNED NULL,
  fecha_envio DATETIME NULL,
  fecha_entrega DATETIME NULL,
  fecha_registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  legado TINYINT(1) NOT NULL DEFAULT 0,
  CONSTRAINT fk_pe_subpedido FOREIGN KEY (pedido_vendedor_id) REFERENCES pedido_vendedores(id),
  CONSTRAINT fk_pe_creador FOREIGN KEY (creado_por) REFERENCES usuarios(id),
  CONSTRAINT fk_pe_receptor FOREIGN KEY (entregado_por) REFERENCES usuarios(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS pedido_envio_lineas (
  envio_id INT UNSIGNED NOT NULL,
  pedido_linea_id INT UNSIGNED NOT NULL,
  cantidad INT NOT NULL,
  PRIMARY KEY (envio_id,pedido_linea_id),
  CONSTRAINT fk_pel_envio FOREIGN KEY (envio_id) REFERENCES pedido_envios(id),
  CONSTRAINT fk_pel_linea FOREIGN KEY (pedido_linea_id) REFERENCES pedido_lineas(id),
  CONSTRAINT ck_pel_cantidad CHECK (cantidad > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
