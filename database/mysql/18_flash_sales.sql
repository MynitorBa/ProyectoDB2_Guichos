-- Ventas flash por oferta/vendedor. Migración aditiva e idempotente.
CREATE TABLE IF NOT EXISTS promociones_flash (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  oferta_id INT UNSIGNED NOT NULL,
  creado_por INT UNSIGNED NOT NULL,
  precio_promocional DECIMAL(12,2) NOT NULL,
  unidades_totales INT NOT NULL,
  unidades_vendidas INT NOT NULL DEFAULT 0,
  max_por_usuario INT NOT NULL DEFAULT 1,
  segundos_reserva INT NOT NULL DEFAULT 300,
  inicia_en DATETIME NOT NULL,
  finaliza_en DATETIME NOT NULL,
  estado ENUM('programada','activa','finalizada','cancelada') NOT NULL DEFAULT 'programada',
  version INT NOT NULL DEFAULT 1,
  fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_actualizacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  slot_vigente TINYINT GENERATED ALWAYS AS (
    IF(estado IN ('programada','activa'), 1, NULL)
  ) STORED,
  CONSTRAINT fk_pf_oferta FOREIGN KEY (oferta_id) REFERENCES ofertas(id),
  CONSTRAINT fk_pf_creador FOREIGN KEY (creado_por) REFERENCES usuarios(id),
  CONSTRAINT uq_pf_oferta_vigente UNIQUE (oferta_id, slot_vigente),
  CONSTRAINT ck_pf_precio CHECK (precio_promocional > 0),
  CONSTRAINT ck_pf_unidades CHECK (unidades_totales > 0 AND unidades_vendidas BETWEEN 0 AND unidades_totales),
  CONSTRAINT ck_pf_fechas CHECK (finaliza_en > inicia_en),
  CONSTRAINT ck_pf_limites CHECK (max_por_usuario > 0 AND segundos_reserva > 0),
  INDEX ix_pf_estado_fechas (estado, inicia_en, finaliza_en)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS reservas_flash (
  token CHAR(36) NOT NULL PRIMARY KEY,
  promocion_id INT UNSIGNED NOT NULL,
  usuario_id INT UNSIGNED NOT NULL,
  cantidad INT NOT NULL,
  precio_unitario DECIMAL(12,2) NOT NULL,
  estado ENUM('reservada','convertida','expirada','cancelada') NOT NULL DEFAULT 'reservada',
  expira_en DATETIME NOT NULL,
  pedido_id INT UNSIGNED NULL,
  fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_actualizacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  slot_activo TINYINT GENERATED ALWAYS AS (IF(estado='reservada', 1, NULL)) STORED,
  CONSTRAINT fk_rf_promocion FOREIGN KEY (promocion_id) REFERENCES promociones_flash(id),
  CONSTRAINT fk_rf_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
  CONSTRAINT fk_rf_pedido FOREIGN KEY (pedido_id) REFERENCES pedidos(id),
  CONSTRAINT uq_rf_usuario_activo UNIQUE (promocion_id, usuario_id, slot_activo),
  CONSTRAINT ck_rf_cantidad CHECK (cantidad > 0),
  CONSTRAINT ck_rf_precio CHECK (precio_unitario > 0),
  INDEX ix_rf_expiracion (estado, expira_en),
  INDEX ix_rf_pedido (pedido_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
