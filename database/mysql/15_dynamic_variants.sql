-- Registro relacional mínimo para identidades de variante cuyo detalle vive en MongoDB.

CREATE TABLE IF NOT EXISTS producto_variante_referencias (
  id                       INT UNSIGNED NOT NULL AUTO_INCREMENT,
  producto_referencia_id   INT UNSIGNED NOT NULL,
  variante_ref             CHAR(24) NOT NULL,
  fecha_registro           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_pvr_variante_ref (variante_ref),
  KEY idx_pvr_producto (producto_referencia_id),
  CONSTRAINT fk_pvr_producto FOREIGN KEY (producto_referencia_id)
    REFERENCES producto_referencias(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
