-- Migración: variantes (color + talla) en solicitudes de catálogo
-- Ejecutar una sola vez después de 15_variants.sql

ALTER TABLE solicitudes_catalogo
  ADD COLUMN variante_color VARCHAR(50) NOT NULL DEFAULT '',
  ADD COLUMN variante_talla VARCHAR(20) NOT NULL DEFAULT '';
