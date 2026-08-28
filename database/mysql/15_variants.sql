-- Migración: variantes de producto (color + talla) por oferta
-- Ejecutar una sola vez sobre la base de datos existente.

ALTER TABLE ofertas
  ADD COLUMN variante_color VARCHAR(50) NOT NULL DEFAULT '',
  ADD COLUMN variante_talla VARCHAR(20) NOT NULL DEFAULT '';

-- La restricción anterior solo permitía un vendedor por producto.
-- La nueva permite múltiples variantes del mismo vendedor para el mismo producto.
ALTER TABLE ofertas
  DROP INDEX uq_oferta_vendedor_producto,
  ADD UNIQUE INDEX uq_oferta_variante (producto_ref, vendedor_id, variante_color, variante_talla);
