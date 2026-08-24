-- =============================================================================
-- TiendaYa — Migración Fase 1: integridad y DDL reproducible
--
-- Se ejecuta también en instalaciones nuevas. Todas las operaciones que agregan
-- objetos consultan information_schema para poder repetirse sin duplicarlos.
-- Antes de agregar FKs se aborta si existen referencias huérfanas.
-- =============================================================================

USE tiendaya;

CREATE TABLE IF NOT EXISTS notificaciones (
  id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
  usuario_id     INT UNSIGNED NOT NULL,
  tipo           VARCHAR(50)  NOT NULL,
  titulo         VARCHAR(200) NOT NULL,
  mensaje        TEXT         NOT NULL,
  leida          TINYINT(1)   NOT NULL DEFAULT 0,
  pedido_id      INT UNSIGNED NULL,
  fecha_creacion DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DELIMITER //

DROP PROCEDURE IF EXISTS sp_aplicar_integridad_fase1 //
CREATE PROCEDURE sp_aplicar_integridad_fase1()
BEGIN
  DECLARE v_count INT DEFAULT 0;

  SELECT COUNT(*) INTO v_count
  FROM movimientos_inventario mi
  LEFT JOIN pedidos p ON p.id = mi.pedido_id
  WHERE mi.pedido_id IS NOT NULL AND p.id IS NULL;
  IF v_count > 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Fase 1 abortada: movimientos con pedido_id huerfano';
  END IF;

  SELECT COUNT(*) INTO v_count
  FROM movimientos_inventario mi
  LEFT JOIN usuarios u ON u.id = mi.usuario_id
  WHERE mi.usuario_id IS NOT NULL AND u.id IS NULL;
  IF v_count > 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Fase 1 abortada: movimientos con usuario_id huerfano';
  END IF;

  SELECT COUNT(*) INTO v_count
  FROM notificaciones n
  LEFT JOIN usuarios u ON u.id = n.usuario_id
  WHERE u.id IS NULL;
  IF v_count > 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Fase 1 abortada: notificaciones con usuario_id huerfano';
  END IF;

  SELECT COUNT(*) INTO v_count
  FROM notificaciones n
  LEFT JOIN pedidos p ON p.id = n.pedido_id
  WHERE n.pedido_id IS NOT NULL AND p.id IS NULL;
  IF v_count > 0 THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Fase 1 abortada: notificaciones con pedido_id huerfano';
  END IF;

  -- La tabla creada por versiones anteriores usaba INT con signo. Las FKs
  -- requieren exactamente el mismo tipo que usuarios.id y pedidos.id.
  ALTER TABLE notificaciones
    MODIFY id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    MODIFY usuario_id INT UNSIGNED NOT NULL,
    MODIFY pedido_id INT UNSIGNED NULL;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND CONSTRAINT_NAME = 'fk_mi_pedido'
  ) THEN
    ALTER TABLE movimientos_inventario
      ADD CONSTRAINT fk_mi_pedido
      FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE SET NULL;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND CONSTRAINT_NAME = 'fk_mi_usuario'
  ) THEN
    ALTER TABLE movimientos_inventario
      ADD CONSTRAINT fk_mi_usuario
      FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND CONSTRAINT_NAME = 'fk_notif_usuario'
  ) THEN
    ALTER TABLE notificaciones
      ADD CONSTRAINT fk_notif_usuario
      FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND CONSTRAINT_NAME = 'fk_notif_pedido'
  ) THEN
    ALTER TABLE notificaciones
      ADD CONSTRAINT fk_notif_pedido
      FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE SET NULL;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'notificaciones'
      AND INDEX_NAME = 'idx_notif_usuario_leida_fecha'
  ) THEN
    ALTER TABLE notificaciones
      ADD INDEX idx_notif_usuario_leida_fecha
        (usuario_id, leida, fecha_creacion);
  END IF;
END //

CALL sp_aplicar_integridad_fase1() //
DROP PROCEDURE sp_aplicar_integridad_fase1 //

DELIMITER ;
