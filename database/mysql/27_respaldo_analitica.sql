-- Plan B de Cassandra. Proyecciones derivadas de pedidos y pagos MySQL.
-- No reemplazan las transacciones comerciales ni el Outbox.
CREATE TABLE IF NOT EXISTS analitica_productos_semana (
  semana_inicio DATE NOT NULL,
  producto_ref CHAR(24) NOT NULL,
  producto_nombre_snapshot VARCHAR(255) NULL,
  imagen_snapshot TEXT NULL,
  unidades_vendidas BIGINT NOT NULL,
  ingresos_brutos DECIMAL(18,2) NOT NULL,
  ingresos_reembolsados DECIMAL(18,2) NOT NULL,
  ingresos_netos DECIMAL(18,2) NOT NULL,
  pedidos_distintos BIGINT NOT NULL,
  vendedores_distintos BIGINT NOT NULL,
  ofertas_distintas BIGINT NOT NULL,
  unidades_flash BIGINT NOT NULL,
  actualizado_en DATETIME(6) NOT NULL,
  PRIMARY KEY (semana_inicio, producto_ref),
  KEY idx_analitica_producto_tiempo (producto_ref, semana_inicio)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS analitica_productos_vendedor_semana (
  vendedor_id BIGINT NOT NULL,
  producto_ref CHAR(24) NOT NULL,
  semana_inicio DATE NOT NULL,
  producto_nombre_snapshot VARCHAR(255) NULL,
  unidades_vendidas BIGINT NOT NULL,
  ingresos_brutos DECIMAL(18,2) NOT NULL,
  ingresos_reembolsados DECIMAL(18,2) NOT NULL,
  ingresos_netos DECIMAL(18,2) NOT NULL,
  pedidos_distintos BIGINT NOT NULL,
  ofertas_distintas BIGINT NOT NULL,
  unidades_flash BIGINT NOT NULL,
  actualizado_en DATETIME(6) NOT NULL,
  PRIMARY KEY (vendedor_id, producto_ref, semana_inicio),
  KEY idx_analitica_vendedor_semana (vendedor_id, semana_inicio),
  KEY idx_analitica_productos_vendedor_semana (semana_inicio)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS analitica_ofertas_vendedor_semana (
  vendedor_id BIGINT NOT NULL,
  semana_inicio DATE NOT NULL,
  oferta_id BIGINT NOT NULL,
  producto_ref CHAR(24) NOT NULL,
  producto_nombre_snapshot VARCHAR(255) NULL,
  sku_snapshot VARCHAR(120) NULL,
  unidades_vendidas BIGINT NOT NULL,
  ingresos_brutos DECIMAL(18,2) NOT NULL,
  ingresos_reembolsados DECIMAL(18,2) NOT NULL,
  ingresos_netos DECIMAL(18,2) NOT NULL,
  pedidos_distintos BIGINT NOT NULL,
  unidades_flash BIGINT NOT NULL,
  actualizado_en DATETIME(6) NOT NULL,
  PRIMARY KEY (vendedor_id, semana_inicio, oferta_id),
  KEY idx_analitica_oferta (oferta_id, semana_inicio),
  KEY idx_analitica_ofertas_semana (semana_inicio)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Evita presentar tablas recién creadas pero vacías como estadísticas reales.
CREATE TABLE IF NOT EXISTS analitica_respaldo_control (
  id TINYINT NOT NULL PRIMARY KEY,
  backfill_completo BOOLEAN NOT NULL DEFAULT FALSE,
  actualizado_en DATETIME(6) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
INSERT IGNORE INTO analitica_respaldo_control (id, backfill_completo) VALUES (1, FALSE);

-- El extractor acota pedidos por vigencia UTC; sin este índice recorrería todo
-- el historial comercial por cada semana recalculada. Crear solo si falta.
SET @idx_fecha = (SELECT COUNT(*) FROM information_schema.statistics
                  WHERE table_schema=DATABASE() AND table_name='pedidos'
                    AND index_name='idx_pedidos_fecha_creacion');
SET @sql = IF(@idx_fecha=0,
              'ALTER TABLE pedidos ADD INDEX idx_pedidos_fecha_creacion (fecha_creacion)',
              'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Un destino independiente permite actualizar el respaldo aunque Cassandra falle.
ALTER TABLE outbox_eventos
  MODIFY COLUMN destino ENUM('mongo','busqueda','cassandra','neo4j','redis','catalogo','analitica_mysql')
  NOT NULL DEFAULT 'mongo';
