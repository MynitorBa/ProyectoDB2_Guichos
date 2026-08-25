-- Solicitudes controladas de productos y ofertas enviadas por vendedores.

CREATE TABLE IF NOT EXISTS solicitudes_catalogo (
  id                       BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  vendedor_id              INT UNSIGNED NOT NULL,
  tipo                     ENUM('producto_nuevo','oferta_existente') NOT NULL,
  estado                   ENUM('pendiente','aprobada','rechazada','cancelada') NOT NULL DEFAULT 'pendiente',
  producto_ref_solicitado  CHAR(24) NULL,
  nombre                   VARCHAR(200) NULL,
  descripcion              TEXT NULL,
  atributos                JSON NOT NULL,
  sku_propuesto            VARCHAR(50) NULL,
  precio_propuesto         DECIMAL(12,2) NOT NULL,
  stock_propuesto          INT UNSIGNED NOT NULL,
  observaciones_vendedor   TEXT NULL,
  observaciones_admin      TEXT NULL,
  revisada_por             INT UNSIGNED NULL,
  producto_ref_resultado   CHAR(24) NULL,
  oferta_id_resultado      INT UNSIGNED NULL,
  fecha_creacion           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_actualizacion      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  fecha_revision           DATETIME NULL,
  PRIMARY KEY (id),
  KEY idx_sc_vendedor_estado (vendedor_id, estado, fecha_creacion),
  KEY idx_sc_admin_estado (estado, fecha_creacion),
  KEY idx_sc_producto_solicitado (producto_ref_solicitado),
  CONSTRAINT fk_sc_vendedor FOREIGN KEY (vendedor_id) REFERENCES vendedores(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sc_producto_solicitado FOREIGN KEY (producto_ref_solicitado)
    REFERENCES producto_referencias(producto_ref) ON DELETE RESTRICT,
  CONSTRAINT fk_sc_revisada_por FOREIGN KEY (revisada_por) REFERENCES usuarios(id) ON DELETE SET NULL,
  CONSTRAINT fk_sc_producto_resultado FOREIGN KEY (producto_ref_resultado)
    REFERENCES producto_referencias(producto_ref) ON DELETE RESTRICT,
  CONSTRAINT fk_sc_oferta_resultado FOREIGN KEY (oferta_id_resultado) REFERENCES ofertas(id) ON DELETE RESTRICT,
  CONSTRAINT ck_sc_precio CHECK (precio_propuesto > 0),
  CONSTRAINT ck_sc_tipo_datos CHECK (
    (tipo = 'producto_nuevo' AND producto_ref_solicitado IS NULL AND nombre IS NOT NULL)
    OR
    (tipo = 'oferta_existente' AND producto_ref_solicitado IS NOT NULL AND nombre IS NULL)
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS solicitud_catalogo_categorias (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  solicitud_id  BIGINT UNSIGNED NOT NULL,
  categoria_id  INT UNSIGNED NOT NULL,
  orden         SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uq_scc_solicitud_categoria (solicitud_id, categoria_id),
  UNIQUE KEY uq_scc_solicitud_orden (solicitud_id, orden),
  KEY idx_scc_categoria (categoria_id),
  CONSTRAINT fk_scc_solicitud FOREIGN KEY (solicitud_id) REFERENCES solicitudes_catalogo(id) ON DELETE CASCADE,
  CONSTRAINT fk_scc_categoria FOREIGN KEY (categoria_id) REFERENCES categorias(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS solicitud_catalogo_imagenes (
  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  solicitud_id        BIGINT UNSIGNED NOT NULL,
  producto_imagen_id  INT UNSIGNED NOT NULL,
  orden               SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uq_sci_solicitud_orden (solicitud_id, orden),
  UNIQUE KEY uq_sci_imagen (producto_imagen_id),
  CONSTRAINT fk_sci_solicitud FOREIGN KEY (solicitud_id) REFERENCES solicitudes_catalogo(id) ON DELETE CASCADE,
  CONSTRAINT fk_sci_imagen FOREIGN KEY (producto_imagen_id) REFERENCES producto_imagenes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
