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
-- Idempotente: solo elige un candidato cuando todavía no hay uno configurado.
-- El subquery y LIMIT evitan marcar accidentalmente dos vendedores si el correo
-- y el nombre comercial pertenecen a filas distintas.
UPDATE vendedores
SET es_tiendaya = 1
WHERE id = (
    SELECT candidato.id
    FROM (
        SELECT v.id
        FROM vendedores v
        JOIN usuarios u ON u.id = v.usuario_id
        WHERE u.email = 'admin@tiendaya.gt'
           OR v.nombre_comercial = 'TiendaYa'
        ORDER BY (u.email = 'admin@tiendaya.gt') DESC, v.id
        LIMIT 1
    ) AS candidato
)
AND NOT EXISTS (
    SELECT 1
    FROM (SELECT es_tiendaya FROM vendedores) AS existentes
    WHERE existentes.es_tiendaya = 1
);
