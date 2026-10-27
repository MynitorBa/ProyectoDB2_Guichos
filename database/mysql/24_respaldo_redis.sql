-- =============================================================================
-- Migración 24: respaldo en MySQL del carrito y de las ventas flash cuando
-- Redis no está disponible (plan B). Aditiva e idempotente.
--
-- Redis sigue siendo el camino rápido. Cada cambio del carrito se copia aquí;
-- si Redis no responde, el carrito se lee y escribe en estas tablas y se marca
-- pendiente_redis = 1 para que, cuando Redis vuelva, se reconstruya desde aquí.
-- =============================================================================

CREATE TABLE IF NOT EXISTS carritos_respaldo (
  usuario_id INT UNSIGNED NOT NULL,
  pendiente_redis TINYINT(1) NOT NULL DEFAULT 0,
  expira_en DATETIME NOT NULL,
  actualizado_en DATETIME(6) NOT NULL,
  PRIMARY KEY (usuario_id),
  KEY idx_carritos_respaldo_pendiente (pendiente_redis),
  CONSTRAINT fk_carritos_respaldo_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- datos guarda exactamente el mismo JSON que el campo del HASH carrito:{usuario}
-- en Redis (cantidad, precio_al_agregar, producto_ref y, si aplica, la reserva flash).
CREATE TABLE IF NOT EXISTS carritos_respaldo_items (
  usuario_id INT UNSIGNED NOT NULL,
  oferta_id INT UNSIGNED NOT NULL,
  datos JSON NOT NULL,
  PRIMARY KEY (usuario_id, oferta_id),
  CONSTRAINT fk_carritos_respaldo_items_carrito FOREIGN KEY (usuario_id)
    REFERENCES carritos_respaldo(usuario_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Promociones cuyas reservas cambiaron solo en MySQL mientras Redis estaba
-- caído. El worker flash borra su estado en Redis y lo reconstruye desde MySQL.
CREATE TABLE IF NOT EXISTS flash_resincronizar (
  promocion_id INT UNSIGNED NOT NULL,
  creado_en DATETIME(6) NOT NULL,
  PRIMARY KEY (promocion_id),
  CONSTRAINT fk_flash_resincronizar_promocion FOREIGN KEY (promocion_id)
    REFERENCES promociones_flash(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
