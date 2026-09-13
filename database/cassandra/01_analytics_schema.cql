CREATE KEYSPACE IF NOT EXISTS tiendaya_analytics
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

USE tiendaya_analytics;

-- Detalle cronológico. La segunda clustering key evita colisiones cuando dos
-- líneas se confirman en el mismo instante.
CREATE TABLE IF NOT EXISTS ventas_producto_semana (
    producto_ref text,
    semana_inicio date,
    fecha_hora timestamp,
    pedido_linea_id bigint,
    pedido_id bigint,
    oferta_id bigint,
    vendedor_id bigint,
    variante_id bigint,
    sku_snapshot text,
    producto_nombre_snapshot text,
    vendedor_nombre_snapshot text,
    cantidad int,
    precio_unitario decimal,
    subtotal decimal,
    tipo_venta text,
    promocion_flash_id bigint,
    estado_pago text,
    PRIMARY KEY ((producto_ref, semana_inicio), fecha_hora, pedido_linea_id)
) WITH CLUSTERING ORDER BY (fecha_hora DESC, pedido_linea_id DESC);

-- Ranking global de productos de una semana. Es una proyección materializada
-- por la aplicación; Cassandra no realiza JOIN ni GROUP BY transaccional.
CREATE TABLE IF NOT EXISTS resumen_productos_semana (
    semana_inicio date,
    producto_ref text,
    producto_nombre_snapshot text,
    imagen_snapshot text,
    unidades_vendidas bigint,
    ingresos_brutos decimal,
    ingresos_reembolsados decimal,
    ingresos_netos decimal,
    pedidos_distintos bigint,
    vendedores_distintos bigint,
    ofertas_distintas bigint,
    unidades_flash bigint,
    actualizado_en timestamp,
    PRIMARY KEY ((semana_inicio), producto_ref)
);

-- Panel privado del vendedor, desglosado por cada oferta.
CREATE TABLE IF NOT EXISTS resumen_ofertas_vendedor_semana (
    vendedor_id bigint,
    semana_inicio date,
    oferta_id bigint,
    producto_ref text,
    producto_nombre_snapshot text,
    sku_snapshot text,
    unidades_vendidas bigint,
    ingresos_brutos decimal,
    ingresos_reembolsados decimal,
    ingresos_netos decimal,
    pedidos_distintos bigint,
    unidades_flash bigint,
    actualizado_en timestamp,
    PRIMARY KEY ((vendedor_id, semana_inicio), oferta_id)
);
