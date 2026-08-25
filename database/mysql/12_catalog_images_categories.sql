-- Extensión incremental del catálogo final: imágenes BLOB y categorías múltiples.

CREATE TABLE IF NOT EXISTS producto_imagenes (
  id                      INT UNSIGNED NOT NULL AUTO_INCREMENT,
  producto_referencia_id  INT UNSIGNED NULL,
  datos                   LONGBLOB NOT NULL,
  mime_type               VARCHAR(50) NOT NULL DEFAULT 'image/jpeg',
  orden                   SMALLINT NOT NULL DEFAULT 0,
  fecha_creacion          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_pi_referencia_orden (producto_referencia_id, orden),
  CONSTRAINT fk_pi_referencia FOREIGN KEY (producto_referencia_id)
    REFERENCES producto_referencias(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS producto_referencia_categorias (
  id                      INT UNSIGNED NOT NULL AUTO_INCREMENT,
  producto_referencia_id  INT UNSIGNED NOT NULL,
  categoria_id            INT UNSIGNED NOT NULL,
  es_principal            TINYINT(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uq_prc_referencia_categoria (producto_referencia_id, categoria_id),
  KEY idx_prc_categoria (categoria_id, producto_referencia_id),
  CONSTRAINT fk_prc_referencia FOREIGN KEY (producto_referencia_id)
    REFERENCES producto_referencias(id) ON DELETE CASCADE,
  CONSTRAINT fk_prc_categoria FOREIGN KEY (categoria_id)
    REFERENCES categorias(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO producto_referencia_categorias
  (producto_referencia_id, categoria_id, es_principal)
SELECT id, categoria_id, 1
FROM producto_referencias;
