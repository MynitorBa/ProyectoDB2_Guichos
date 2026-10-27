-- =============================================================================
-- Migración 26: caché de recomendaciones de co-compra (plan B de Neo4j).
-- Aditiva e idempotente.
--
-- Cada hora se guarda aquí, para cada producto, el resultado del recorrido
-- «quienes compraron X también compraron Y» de Neo4j. Si Neo4j no responde,
-- las recomendaciones se leen de esta tabla; precio, stock y categoría se
-- siguen validando al momento contra MySQL y el catálogo.
-- =============================================================================

CREATE TABLE IF NOT EXISTS recomendaciones_cache (
  producto_ref CHAR(24) NOT NULL,
  recomendado_ref CHAR(24) NOT NULL,
  compradores_comunes INT UNSIGNED NOT NULL,
  calculado_en DATETIME(6) NOT NULL,
  PRIMARY KEY (producto_ref, recomendado_ref),
  KEY idx_recomendaciones_cache_orden (producto_ref, compradores_comunes)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
