-- Historial temporal complementario para reconstruir ofertas completas.
SET time_zone = '+00:00';

CREATE TABLE IF NOT EXISTS oferta_estados_historial (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  oferta_id      INT UNSIGNED    NOT NULL,
  vendedor_id    INT UNSIGNED    NOT NULL,
  sku            VARCHAR(50)     NOT NULL,
  estado         ENUM('borrador','activa','pausada','descontinuada') NOT NULL,
  vigente_desde  DATETIME(6)     NOT NULL,
  vigente_hasta  DATETIME(6)     NULL,
  cambiado_por   INT UNSIGNED    NULL,
  motivo         VARCHAR(200)    NULL,
  fecha_registro DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  es_vigente     TINYINT GENERATED ALWAYS AS (IF(vigente_hasta IS NULL, 1, NULL)) STORED,
  PRIMARY KEY (id),
  UNIQUE KEY uq_estado_vigente_oferta (oferta_id, es_vigente),
  KEY idx_estado_oferta_desde (oferta_id, vigente_desde),
  CONSTRAINT fk_oeh_oferta FOREIGN KEY (oferta_id) REFERENCES ofertas(id) ON DELETE RESTRICT,
  CONSTRAINT fk_oeh_vendedor FOREIGN KEY (vendedor_id) REFERENCES vendedores(id) ON DELETE RESTRICT,
  CONSTRAINT fk_oeh_usuario FOREIGN KEY (cambiado_por) REFERENCES usuarios(id) ON DELETE SET NULL,
  CONSTRAINT ck_oeh_intervalo CHECK (vigente_hasta IS NULL OR vigente_hasta > vigente_desde)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS inventario_saldos_historial (
  id                    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  inventario_id         INT UNSIGNED    NOT NULL,
  cantidad_disponible   INT             NOT NULL,
  cantidad_reservada    INT             NOT NULL,
  vigente_desde         DATETIME(6)     NOT NULL,
  vigente_hasta         DATETIME(6)     NULL,
  cambiado_por          INT UNSIGNED    NULL,
  motivo                VARCHAR(200)    NULL,
  fecha_registro        DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  es_vigente            TINYINT GENERATED ALWAYS AS (IF(vigente_hasta IS NULL, 1, NULL)) STORED,
  PRIMARY KEY (id),
  UNIQUE KEY uq_saldo_vigente_inventario (inventario_id, es_vigente),
  KEY idx_saldo_inventario_desde (inventario_id, vigente_desde),
  CONSTRAINT fk_ish_inventario FOREIGN KEY (inventario_id) REFERENCES inventario(id) ON DELETE RESTRICT,
  CONSTRAINT fk_ish_usuario FOREIGN KEY (cambiado_por) REFERENCES usuarios(id) ON DELETE SET NULL,
  CONSTRAINT ck_ish_cantidades CHECK (cantidad_disponible >= 0 AND cantidad_reservada >= 0),
  CONSTRAINT ck_ish_intervalo CHECK (vigente_hasta IS NULL OR vigente_hasta > vigente_desde)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO oferta_estados_historial (
  oferta_id, vendedor_id, sku, estado, vigente_desde, motivo
)
SELECT o.id, o.vendedor_id, o.sku, o.estado, o.fecha_creacion,
       'Estado inicial reconstruido durante instalación'
FROM ofertas o
WHERE NOT EXISTS (
  SELECT 1 FROM oferta_estados_historial h WHERE h.oferta_id = o.id
);

INSERT INTO inventario_saldos_historial (
  inventario_id, cantidad_disponible, cantidad_reservada, vigente_desde, motivo
)
SELECT i.id, i.cantidad_disponible, i.cantidad_reservada,
       COALESCE(o.fecha_creacion, i.fecha_actualizacion),
       'Saldo inicial reconstruido durante instalación'
FROM inventario i
LEFT JOIN ofertas o ON o.id = i.oferta_id
WHERE NOT EXISTS (
  SELECT 1 FROM inventario_saldos_historial h WHERE h.inventario_id = i.id
);
