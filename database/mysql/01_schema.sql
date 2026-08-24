-- =============================================================================
-- TiendaYa — Esquema relacional normalizado a 3FN
-- Motor: InnoDB | Charset: utf8mb4 | Collation: utf8mb4_unicode_ci
-- =============================================================================

SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;
SET time_zone = '+00:00';
SET foreign_key_checks = 0;

CREATE DATABASE IF NOT EXISTS tiendaya
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE tiendaya;

-- =============================================================================
-- 1. USUARIOS Y SEGURIDAD
-- =============================================================================

CREATE TABLE IF NOT EXISTS roles (
  id         TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
  nombre     VARCHAR(30)      NOT NULL,
  descripcion VARCHAR(120)    NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_roles_nombre (nombre)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS usuarios (
  id              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
  email           VARCHAR(254)    NOT NULL,
  password_hash   VARCHAR(255)    NOT NULL,
  nombre          VARCHAR(100)    NOT NULL,
  apellido        VARCHAR(100)    NOT NULL,
  telefono        VARCHAR(20)     NULL,
  estado          ENUM('activo','inactivo','suspendido') NOT NULL DEFAULT 'activo',
  email_verificado TINYINT(1)     NOT NULL DEFAULT 0,
  fecha_alta      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_actualizacion DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_usuarios_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tabla puente N:M usuario ↔ rol. Un usuario puede tener varios roles
-- (p.ej. alguien que es vendedor y comprador a la vez).
CREATE TABLE IF NOT EXISTS usuario_rol (
  usuario_id  INT UNSIGNED    NOT NULL,
  rol_id      TINYINT UNSIGNED NOT NULL,
  asignado_en DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (usuario_id, rol_id),
  CONSTRAINT fk_ur_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
  CONSTRAINT fk_ur_rol     FOREIGN KEY (rol_id)     REFERENCES roles(id)    ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- 2. DIRECCIONES
-- =============================================================================

CREATE TABLE IF NOT EXISTS direcciones (
  id              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
  usuario_id      INT UNSIGNED    NOT NULL,
  tipo            ENUM('envio','facturacion') NOT NULL DEFAULT 'envio',
  pais            VARCHAR(60)     NOT NULL DEFAULT 'Guatemala',
  departamento    VARCHAR(60)     NOT NULL,
  municipio       VARCHAR(60)     NOT NULL,
  linea1          VARCHAR(200)    NOT NULL,
  linea2          VARCHAR(200)    NULL,
  codigo_postal   VARCHAR(10)     NULL,
  es_predeterminada TINYINT(1)   NOT NULL DEFAULT 0,
  activa          TINYINT(1)     NOT NULL DEFAULT 1,
  PRIMARY KEY (id),
  CONSTRAINT fk_dir_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- 3. VENDEDORES
-- =============================================================================

CREATE TABLE IF NOT EXISTS vendedores (
  id                  INT UNSIGNED    NOT NULL AUTO_INCREMENT,
  usuario_id          INT UNSIGNED    NOT NULL,
  nombre_comercial    VARCHAR(150)    NOT NULL,
  nit                 VARCHAR(20)     NOT NULL,
  descripcion         TEXT            NULL,
  logo_url            VARCHAR(500)    NULL,
  estado_verificacion ENUM('pendiente','verificado','rechazado') NOT NULL DEFAULT 'pendiente',
  fecha_registro      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_vendedores_nit (nit),
  UNIQUE KEY uq_vendedores_usuario (usuario_id),
  CONSTRAINT fk_ven_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- 4. CATÁLOGO RELACIONAL
-- =============================================================================

CREATE TABLE IF NOT EXISTS categorias (
  id                INT UNSIGNED    NOT NULL AUTO_INCREMENT,
  categoria_padre_id INT UNSIGNED   NULL,
  nombre            VARCHAR(100)    NOT NULL,
  slug              VARCHAR(120)    NOT NULL,
  descripcion       TEXT            NULL,
  imagen_url        VARCHAR(500)    NULL,
  activa            TINYINT(1)      NOT NULL DEFAULT 1,
  orden             SMALLINT        NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uq_categorias_slug (slug),
  CONSTRAINT fk_cat_padre FOREIGN KEY (categoria_padre_id) REFERENCES categorias(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS productos (
  id              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
  sku             VARCHAR(50)     NOT NULL,
  nombre          VARCHAR(200)    NOT NULL,
  descripcion     TEXT            NULL,
  precio          DECIMAL(10,2)   NOT NULL CHECK (precio >= 0),
  categoria_id    INT UNSIGNED    NOT NULL,
  vendedor_id     INT UNSIGNED    NOT NULL,
  -- producto_ref se llena al migrar a Mongo (CHAR(24) = ObjectId hexadecimal)
  producto_ref    CHAR(24)        NULL COMMENT 'ObjectId en MongoDB tras la migración',
  estado          ENUM('activo','inactivo','borrador','descontinuado') NOT NULL DEFAULT 'activo',
  fecha_creacion  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_actualizacion DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_productos_sku (sku),
  CONSTRAINT fk_prod_categoria FOREIGN KEY (categoria_id) REFERENCES categorias(id) ON DELETE RESTRICT,
  CONSTRAINT fk_prod_vendedor  FOREIGN KEY (vendedor_id)  REFERENCES vendedores(id)  ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS producto_imagenes (
  id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
  producto_id INT UNSIGNED    NOT NULL,
  url         VARCHAR(500)    NOT NULL,
  alt_text    VARCHAR(200)    NULL,
  orden       TINYINT UNSIGNED NOT NULL DEFAULT 0,
  es_principal TINYINT(1)    NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  CONSTRAINT fk_pi_producto FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Oferta transaccional: quién vende el producto documental, a qué precio y
-- bajo qué estado comercial. producto_ref apunta lógicamente a MongoDB.
CREATE TABLE IF NOT EXISTS ofertas (
  id                  INT UNSIGNED    NOT NULL AUTO_INCREMENT,
  producto_ref        CHAR(24)        NOT NULL,
  vendedor_id         INT UNSIGNED    NOT NULL,
  sku                 VARCHAR(50)     NOT NULL,
  precio_actual       DECIMAL(12,2)   NOT NULL CHECK (precio_actual >= 0),
  moneda              CHAR(3)         NOT NULL DEFAULT 'GTQ',
  estado              ENUM('borrador','activa','pausada','descontinuada') NOT NULL DEFAULT 'activa',
  version             INT UNSIGNED    NOT NULL DEFAULT 1 CHECK (version > 0),
  fecha_creacion      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_actualizacion DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_oferta_vendedor_sku (vendedor_id, sku),
  UNIQUE KEY uq_oferta_vendedor_producto (vendedor_id, producto_ref),
  KEY idx_oferta_producto_ref (producto_ref),
  CONSTRAINT fk_oferta_vendedor FOREIGN KEY (vendedor_id) REFERENCES vendedores(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS oferta_precios_historial (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  oferta_id      INT UNSIGNED    NOT NULL,
  precio         DECIMAL(12,2)   NOT NULL CHECK (precio >= 0),
  moneda         CHAR(3)         NOT NULL DEFAULT 'GTQ',
  vigente_desde  DATETIME(6)     NOT NULL,
  vigente_hasta  DATETIME(6)     NULL,
  cambiado_por   INT UNSIGNED    NULL,
  motivo         VARCHAR(200)    NULL,
  fecha_registro DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  es_vigente     TINYINT GENERATED ALWAYS AS (IF(vigente_hasta IS NULL, 1, NULL)) STORED,
  PRIMARY KEY (id),
  UNIQUE KEY uq_precio_vigente_oferta (oferta_id, es_vigente),
  KEY idx_precio_oferta_desde (oferta_id, vigente_desde),
  CONSTRAINT fk_oph_oferta FOREIGN KEY (oferta_id) REFERENCES ofertas(id) ON DELETE RESTRICT,
  CONSTRAINT fk_oph_usuario FOREIGN KEY (cambiado_por) REFERENCES usuarios(id) ON DELETE SET NULL,
  CONSTRAINT ck_oph_intervalo CHECK (vigente_hasta IS NULL OR vigente_hasta > vigente_desde)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- 5. INVENTARIO
-- =============================================================================

CREATE TABLE IF NOT EXISTS inventario (
  id                  INT UNSIGNED    NOT NULL AUTO_INCREMENT,
  producto_id         INT UNSIGNED    NOT NULL,
  oferta_id           INT UNSIGNED    NULL COMMENT 'FK de transición hacia ofertas',
  cantidad_disponible INT             NOT NULL DEFAULT 0 CHECK (cantidad_disponible >= 0),
  cantidad_reservada  INT             NOT NULL DEFAULT 0 CHECK (cantidad_reservada >= 0),
  punto_reorden       INT             NOT NULL DEFAULT 5,
  bodega              VARCHAR(60)     NOT NULL DEFAULT 'principal',
  fecha_actualizacion DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_inv_producto_bodega (producto_id, bodega),
  KEY idx_inv_oferta_id (oferta_id),
  CONSTRAINT fk_inv_producto FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE CASCADE,
  CONSTRAINT fk_inv_oferta FOREIGN KEY (oferta_id) REFERENCES ofertas(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS movimientos_inventario (
  id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
  producto_id INT UNSIGNED    NOT NULL,
  tipo        ENUM('entrada','salida','ajuste','reserva','liberacion') NOT NULL,
  cantidad    INT             NOT NULL,
  motivo      VARCHAR(100)    NOT NULL,
  pedido_id   INT UNSIGNED    NULL,
  usuario_id  INT UNSIGNED    NULL,
  fecha       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_mi_producto FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE RESTRICT,
  CONSTRAINT fk_mi_usuario  FOREIGN KEY (usuario_id)  REFERENCES usuarios(id)  ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- 6. MÉTODOS DE PAGO
-- =============================================================================

CREATE TABLE IF NOT EXISTS metodos_pago (
  id      TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
  nombre  VARCHAR(60)      NOT NULL,
  activo  TINYINT(1)       NOT NULL DEFAULT 1,
  PRIMARY KEY (id),
  UNIQUE KEY uq_mp_nombre (nombre)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- 7. PEDIDOS
-- =============================================================================

CREATE TABLE IF NOT EXISTS pedidos (
  id              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
  usuario_id      INT UNSIGNED    NOT NULL,
  direccion_id    INT UNSIGNED    NOT NULL,
  estado          ENUM('pendiente','confirmado','enviado','entregado','cancelado','reembolsado')
                  NOT NULL DEFAULT 'pendiente',
  subtotal        DECIMAL(10,2)   NOT NULL CHECK (subtotal >= 0),
  impuestos       DECIMAL(10,2)   NOT NULL DEFAULT 0.00 CHECK (impuestos >= 0),
  total           DECIMAL(10,2)   NOT NULL CHECK (total >= 0),
  notas           TEXT            NULL,
  fecha_creacion  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_actualizacion DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_ped_usuario   FOREIGN KEY (usuario_id)   REFERENCES usuarios(id)    ON DELETE RESTRICT,
  CONSTRAINT fk_ped_direccion FOREIGN KEY (direccion_id) REFERENCES direcciones(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pedido_vendedores (
  id                  INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  pedido_id           INT UNSIGNED  NOT NULL,
  vendedor_id         INT UNSIGNED  NOT NULL,
  estado              ENUM('pendiente','confirmado','preparando','enviado','entregado','cancelado','reembolsado') NOT NULL DEFAULT 'pendiente',
  subtotal            DECIMAL(12,2) NOT NULL DEFAULT 0.00 CHECK (subtotal >= 0),
  costo_envio         DECIMAL(12,2) NOT NULL DEFAULT 0.00 CHECK (costo_envio >= 0),
  fecha_creacion      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_actualizacion DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_pv_pedido_vendedor (pedido_id, vendedor_id),
  KEY idx_pv_vendedor_estado (vendedor_id, estado),
  CONSTRAINT fk_pv_pedido FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE,
  CONSTRAINT fk_pv_vendedor FOREIGN KEY (vendedor_id) REFERENCES vendedores(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pedido_direcciones (
  pedido_id          INT UNSIGNED NOT NULL,
  receptor_nombre    VARCHAR(200) NOT NULL,
  receptor_telefono  VARCHAR(20)  NULL,
  pais               VARCHAR(60)  NOT NULL DEFAULT 'Guatemala',
  departamento       VARCHAR(60)  NOT NULL,
  municipio          VARCHAR(60)  NOT NULL,
  linea1             VARCHAR(200) NOT NULL,
  linea2             VARCHAR(200) NULL,
  codigo_postal      VARCHAR(10)  NULL,
  PRIMARY KEY (pedido_id),
  CONSTRAINT fk_pd_pedido FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Se agrega después de crear pedidos porque movimientos_inventario se define
-- antes para mantener agrupadas las tablas de inventario.
ALTER TABLE movimientos_inventario
  ADD CONSTRAINT fk_mi_pedido FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE SET NULL;

-- precio_unitario se congela al momento de la compra: denormalización deliberada
-- para preservar el historial aunque el producto cambie de precio mañana.
CREATE TABLE IF NOT EXISTS pedido_lineas (
  id              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
  pedido_id       INT UNSIGNED    NOT NULL,
  producto_id     INT UNSIGNED    NULL COMMENT 'FK a productos MySQL; puede quedar NULL si el producto se elimina',
  pedido_vendedor_id INT UNSIGNED NULL,
  oferta_id       INT UNSIGNED    NULL,
  producto_ref    CHAR(24)        NULL COMMENT 'ObjectId en MongoDB del producto al momento de la compra',
  sku_snapshot    VARCHAR(50)     NULL,
  -- Snapshot del producto al momento de la compra
  producto_nombre VARCHAR(200)    NOT NULL COMMENT 'Nombre congelado al comprar',
  vendedor_nombre_snapshot VARCHAR(150) NULL,
  precio_unitario DECIMAL(10,2)   NOT NULL COMMENT 'Precio congelado al comprar; no viola 3FN porque es dato histórico',
  cantidad        SMALLINT UNSIGNED NOT NULL CHECK (cantidad > 0),
  subtotal_linea  DECIMAL(10,2)   NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_pl_pedido  FOREIGN KEY (pedido_id)  REFERENCES pedidos(id)   ON DELETE CASCADE,
  CONSTRAINT fk_pl_producto FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE SET NULL,
  CONSTRAINT fk_pl_pedido_vendedor FOREIGN KEY (pedido_vendedor_id) REFERENCES pedido_vendedores(id) ON DELETE SET NULL,
  CONSTRAINT fk_pl_oferta FOREIGN KEY (oferta_id) REFERENCES ofertas(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- 8. PAGOS
-- =============================================================================

CREATE TABLE IF NOT EXISTS pagos (
  id                  INT UNSIGNED    NOT NULL AUTO_INCREMENT,
  pedido_id           INT UNSIGNED    NOT NULL,
  metodo_pago_id      TINYINT UNSIGNED NOT NULL,
  monto               DECIMAL(10,2)   NOT NULL CHECK (monto > 0),
  estado              ENUM('pendiente','aprobado','rechazado','reembolsado') NOT NULL DEFAULT 'pendiente',
  referencia_transaccion VARCHAR(100)  NULL,
  fecha               DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_pag_pedido  FOREIGN KEY (pedido_id)      REFERENCES pedidos(id)       ON DELETE RESTRICT,
  CONSTRAINT fk_pag_metodo  FOREIGN KEY (metodo_pago_id) REFERENCES metodos_pago(id)  ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- 9. NOTIFICACIONES
-- =============================================================================

CREATE TABLE IF NOT EXISTS notificaciones (
  id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
  usuario_id     INT UNSIGNED NOT NULL,
  tipo           VARCHAR(50)  NOT NULL,
  titulo         VARCHAR(200) NOT NULL,
  mensaje        TEXT         NOT NULL,
  leida          TINYINT(1)   NOT NULL DEFAULT 0,
  pedido_id      INT UNSIGNED NULL,
  fecha_creacion DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_notif_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
  CONSTRAINT fk_notif_pedido  FOREIGN KEY (pedido_id)  REFERENCES pedidos(id)  ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS outbox_eventos (
  id            CHAR(36)       NOT NULL,
  tipo_evento   VARCHAR(100)   NOT NULL,
  agregado_tipo VARCHAR(60)    NOT NULL,
  agregado_id   VARCHAR(64)    NOT NULL,
  producto_ref  CHAR(24)       NULL,
  payload       JSON           NOT NULL,
  estado        ENUM('pendiente','procesando','procesado','error') NOT NULL DEFAULT 'pendiente',
  intentos      SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  ultimo_error  TEXT           NULL,
  creado_en     DATETIME(6)    NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  procesado_en  DATETIME(6)    NULL,
  PRIMARY KEY (id),
  KEY idx_outbox_estado_creado (estado, creado_en),
  KEY idx_outbox_agregado (agregado_tipo, agregado_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- 10. RESEÑAS
-- =============================================================================

CREATE TABLE IF NOT EXISTS resenas (
  id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
  usuario_id  INT UNSIGNED    NOT NULL,
  producto_id INT UNSIGNED    NOT NULL,
  calificacion TINYINT UNSIGNED NOT NULL CHECK (calificacion BETWEEN 1 AND 5),
  comentario  TEXT            NULL,
  aprobada    TINYINT(1)     NOT NULL DEFAULT 0,
  fecha       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_resenas_usuario_producto (usuario_id, producto_id),
  CONSTRAINT fk_res_usuario  FOREIGN KEY (usuario_id)  REFERENCES usuarios(id)  ON DELETE CASCADE,
  CONSTRAINT fk_res_producto FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- 11. CARRITO TEMPORAL EN SQL (migra a Redis en Entrega 2)
-- Nota: este carrito persiste en la sesión del usuario. En la Entrega 2 se
-- reemplazará por Redis para obtener expiración automática y menor latencia.
-- =============================================================================

CREATE TABLE IF NOT EXISTS carritos (
  id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
  usuario_id  INT UNSIGNED    NOT NULL,
  estado      ENUM('activo','abandonado','convertido') NOT NULL DEFAULT 'activo',
  fecha_creacion      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_actualizacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_carritos_usuario_activo (usuario_id, estado),
  CONSTRAINT fk_cart_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS carrito_items (
  id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
  carrito_id  INT UNSIGNED    NOT NULL,
  producto_id INT UNSIGNED    NOT NULL,
  oferta_id   INT UNSIGNED    NULL COMMENT 'Identidad comprable; producto_id queda para compatibilidad',
  producto_ref CHAR(24)       NULL COMMENT 'ObjectId Mongo del producto',
  cantidad    SMALLINT UNSIGNED NOT NULL DEFAULT 1 CHECK (cantidad > 0),
  precio_al_agregar DECIMAL(10,2) NOT NULL COMMENT 'Precio cuando se agregó al carrito',
  fecha_agregado DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_ci_carrito_oferta (carrito_id, oferta_id),
  KEY idx_ci_producto (producto_id),
  CONSTRAINT fk_ci_carrito  FOREIGN KEY (carrito_id)  REFERENCES carritos(id)  ON DELETE CASCADE,
  CONSTRAINT fk_ci_producto FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE CASCADE,
  CONSTRAINT fk_ci_oferta FOREIGN KEY (oferta_id) REFERENCES ofertas(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET foreign_key_checks = 1;
