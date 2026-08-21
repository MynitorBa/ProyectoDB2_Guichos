-- =============================================================================
-- TiendaYa — Índices adicionales
-- Los índices de PK y UK ya se crearon en 01_schema.sql.
-- Aquí van los índices sobre FK y campos de búsqueda frecuente.
-- =============================================================================

USE tiendaya;

-- Justifica: JOIN usuario_rol WHERE usuario_id = ?  (login, cargar roles del usuario)
CREATE INDEX idx_ur_usuario_id       ON usuario_rol (usuario_id);

-- Justifica: GET /users/{id}/addresses  (listar direcciones de un usuario)
CREATE INDEX idx_dir_usuario_id      ON direcciones (usuario_id);

-- Justifica: filtrar productos por categoría en el catálogo
CREATE INDEX idx_prod_categoria_id   ON productos (categoria_id);

-- Justifica: listar productos de un vendedor en su panel
CREATE INDEX idx_prod_vendedor_id    ON productos (vendedor_id);

-- Justifica: filtrar productos por estado (activo / borrador / descontinuado)
CREATE INDEX idx_prod_estado         ON productos (estado);

-- Justifica: imágenes de un producto al cargar la ficha de detalle
CREATE INDEX idx_pi_producto_id      ON producto_imagenes (producto_id);

-- Justifica: consultar stock de un producto al agregar al carrito o hacer checkout
CREATE INDEX idx_inv_producto_id     ON inventario (producto_id);

-- Justifica: auditoría de movimientos por producto (reportes de inventario)
CREATE INDEX idx_mi_producto_id      ON movimientos_inventario (producto_id);
-- Justifica: listar movimientos asociados a un pedido específico
CREATE INDEX idx_mi_pedido_id        ON movimientos_inventario (pedido_id);

-- Justifica: listar pedidos de un usuario en "Mis pedidos"
CREATE INDEX idx_ped_usuario_id      ON pedidos (usuario_id);
-- Justifica: filtrar pedidos por estado en el panel admin
CREATE INDEX idx_ped_estado          ON pedidos (estado);
-- Justifica: ordenar pedidos por fecha para el dashboard
CREATE INDEX idx_ped_fecha_creacion  ON pedidos (fecha_creacion);

-- Justifica: cargar líneas de un pedido al mostrar el detalle
CREATE INDEX idx_pl_pedido_id        ON pedido_lineas (pedido_id);
-- Justifica: rastrear qué pedidos contienen un producto dado
CREATE INDEX idx_pl_producto_id      ON pedido_lineas (producto_id);

-- Justifica: buscar pagos de un pedido (detalle de factura)
CREATE INDEX idx_pag_pedido_id       ON pagos (pedido_id);

-- Justifica: buscar reseñas de un producto (promedio y listado)
CREATE INDEX idx_res_producto_id     ON resenas (producto_id);
-- Justifica: historial de reseñas de un usuario
CREATE INDEX idx_res_usuario_id      ON resenas (usuario_id);

-- Justifica: cargar carrito activo del usuario al entrar al sitio
CREATE INDEX idx_cart_usuario_id     ON carritos (usuario_id);

-- Justifica: listar ítems de un carrito en el sidebar
CREATE INDEX idx_ci_carrito_id       ON carrito_items (carrito_id);
