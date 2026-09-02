-- =============================================================================
-- Migración 16: unicidad de nombre en categorías + columna es_tiendaya
-- =============================================================================

USE tiendaya;

-- ─── 1. Restricción de unicidad en categorias.nombre ─────────────────────────
-- Idempotente: solo agrega el índice si todavía no existe.
SET @cnt = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE table_schema = DATABASE()
      AND table_name   = 'categorias'
      AND index_name   = 'uq_categorias_nombre'
);
SET @sql = IF(@cnt = 0,
    'ALTER TABLE categorias ADD UNIQUE KEY uq_categorias_nombre (nombre)',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ─── 2. Columna es_tiendaya en vendedores ─────────────────────────────────────
-- MySQL no soporta ADD COLUMN IF NOT EXISTS; se usa condicional vía PREPARE.
SET @col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE table_schema = DATABASE()
      AND table_name   = 'vendedores'
      AND column_name  = 'es_tiendaya'
);
SET @sql = IF(@col = 0,
    'ALTER TABLE vendedores ADD COLUMN es_tiendaya TINYINT(1) NOT NULL DEFAULT 0 COMMENT ''TRUE si este es el perfil del vendedor propio de TiendaYa''',
    'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ─── 3. Marcar al vendedor propio de TiendaYa ────────────────────────────────
-- Idempotente: usa nombre_comercial como criterio; si no existe aún, no hace nada.
UPDATE vendedores v
    JOIN usuarios u ON u.id = v.usuario_id
SET v.es_tiendaya = 1
WHERE u.email = 'admin@tiendaya.gt'
   OR v.nombre_comercial = 'TiendaYa';
