-- Bitácora inmutable para correcciones históricas autorizadas.
-- No ejecuta conciliaciones ni modifica datos comerciales por sí sola.
CREATE TABLE IF NOT EXISTS conciliaciones_historicas (
  id BIGINT NOT NULL AUTO_INCREMENT,
  operacion_id CHAR(36) NOT NULL,
  entorno VARCHAR(40) NOT NULL,
  pedido_id INT UNSIGNED NOT NULL,
  pago_id INT UNSIGNED NOT NULL,
  tipo_conciliacion VARCHAR(80) NOT NULL,
  huella CHAR(64) NOT NULL,
  referencia_cobro VARCHAR(100) NOT NULL,
  responsable_usuario_id INT UNSIGNED NULL,
  estado ENUM('aplicada','revertida') NOT NULL,
  resultado VARCHAR(120) NOT NULL,
  datos_auditoria JSON NOT NULL,
  creado_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  actualizado_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_conciliacion_operacion (operacion_id),
  UNIQUE KEY uq_conciliacion_huella (huella),
  UNIQUE KEY uq_conciliacion_entorno_pedido_tipo
    (entorno, pedido_id, tipo_conciliacion),
  KEY idx_conciliacion_pago (pago_id),
  CONSTRAINT fk_conciliacion_pedido FOREIGN KEY (pedido_id) REFERENCES pedidos(id),
  CONSTRAINT fk_conciliacion_pago FOREIGN KEY (pago_id) REFERENCES pagos(id),
  CONSTRAINT fk_conciliacion_responsable FOREIGN KEY (responsable_usuario_id)
    REFERENCES usuarios(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
