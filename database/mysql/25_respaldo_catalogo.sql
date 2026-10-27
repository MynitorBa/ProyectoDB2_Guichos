-- =============================================================================
-- Migración 25: copia del catálogo de MongoDB en MySQL (plan B de MongoDB).
-- Aditiva e idempotente.
--
-- Cada documento de las colecciones productos y producto_variantes se guarda
-- completo (JSON extendido de BSON, que conserva ObjectId y fechas). Si MongoDB
-- no responde, la tienda lee el catálogo de aquí; el precio y el stock siguen
-- saliendo de las tablas de ofertas e inventario, como siempre.
-- La copia la mantiene el outbox (destino «catalogo») y una reconciliación
-- periódica; no se edita a mano.
-- =============================================================================

CREATE TABLE IF NOT EXISTS catalogo_respaldo (
  coleccion ENUM('productos','producto_variantes') NOT NULL,
  ref CHAR(24) NOT NULL,
  producto_ref CHAR(24) NULL,
  estado VARCHAR(30) NULL,
  documento JSON NOT NULL,
  actualizado_mongo DATETIME(6) NULL,
  copiado_en DATETIME(6) NOT NULL,
  PRIMARY KEY (coleccion, ref),
  KEY idx_catalogo_respaldo_estado (coleccion, estado),
  KEY idx_catalogo_respaldo_producto (producto_ref)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Nuevo destino del outbox. MODIFY con la lista completa es idempotente.
ALTER TABLE outbox_eventos
  MODIFY COLUMN destino ENUM('mongo','busqueda','cassandra','neo4j','redis','catalogo')
  NOT NULL DEFAULT 'mongo';
