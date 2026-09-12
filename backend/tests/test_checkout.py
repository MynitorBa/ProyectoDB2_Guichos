"""
Pruebas del servicio de checkout:
  - checkout exitoso
  - checkout sin stock suficiente
  - concurrencia: dos hilos compran la última unidad → solo uno tiene éxito
"""
import threading
import time
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from bson import ObjectId
from pymongo import MongoClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.services.checkout_service import procesar_checkout, CheckoutError
from app.schemas.checkout import CheckoutItem
from app.core.time import utc_now
from app.models.promocion_flash import PromocionFlash, ReservaFlash

# ── Configuración de la base de datos de pruebas ─────────────────────────────
# En CI o local, conecta a la misma base que tiene datos del seed.
# Para pruebas reales de concurrencia necesitamos un servidor MySQL real,
# no SQLite, porque SQLite no soporta SELECT FOR UPDATE.
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

DB_URL = (
    f"mysql+pymysql://{os.getenv('MYSQL_USER','tiendaya')}:"
    f"{os.getenv('MYSQL_PASSWORD','tiendaya123')}@"
    f"{os.getenv('MYSQL_HOST','localhost')}:"
    f"{os.getenv('MYSQL_PORT','3306')}/"
    f"{os.getenv('MYSQL_DB','tiendaya')}?charset=utf8mb4"
)

engine = create_engine(DB_URL, pool_size=5, max_overflow=10)
TestSession = sessionmaker(bind=engine)

# IDs que existen en el seed
USUARIO_COMPRADOR_ID = 7
DIRECCION_ID         = 2
METODO_PAGO_ID       = 1
OFERTA_TEST_ID       = 65  # Oferta del Mouse Logitech MX Master 3


@pytest.fixture(autouse=True)
def reset_stock():
    """Aísla stock y elimina únicamente pedidos creados por esta prueba."""
    created_order_ids: list[int] = []
    with engine.connect() as conn:
        original_inventory = conn.execute(
            text("""
                SELECT cantidad_disponible, cantidad_reservada FROM inventario
                WHERE oferta_id = :oid AND bodega = 'principal'
            """),
            {'oid': OFERTA_TEST_ID},
        ).one()
        original_stock = original_inventory.cantidad_disponible
        original_reserved = original_inventory.cantidad_reservada
        inventory_id = conn.execute(
            text("""
                SELECT id FROM inventario
                WHERE oferta_id = :oid AND bodega = 'principal'
            """),
            {'oid': OFERTA_TEST_ID},
        ).scalar_one()
        original_balance_id = conn.execute(
            text("""
                SELECT id FROM inventario_saldos_historial
                WHERE inventario_id = :inventory_id AND vigente_hasta IS NULL
            """),
            {'inventory_id': inventory_id},
        ).scalar_one()
        original_max_balance_id = conn.execute(
            text("""
                SELECT COALESCE(MAX(id), 0) FROM inventario_saldos_historial
                WHERE inventario_id = :inventory_id
            """),
            {'inventory_id': inventory_id},
        ).scalar_one()
        producto_ref = conn.execute(
            text('SELECT producto_ref FROM ofertas WHERE id = :oid'),
            {'oid': OFERTA_TEST_ID},
        ).scalar_one()
        conn.execute(
            text("UPDATE inventario SET cantidad_disponible = 30 WHERE oferta_id = :oid AND bodega = 'principal'"),
            {'oid': OFERTA_TEST_ID}
        )
        conn.commit()

    mongo_client = MongoClient(os.getenv('MONGO_URI'))
    mongo_products = mongo_client[os.getenv('MONGO_DB', 'tiendaya')].productos
    original_projection = mongo_products.find_one(
        {'_id': ObjectId(producto_ref)}, {'stock': 1, 'disponible': 1}
    ) or {}

    yield created_order_ids

    if created_order_ids:
        # Los IDs provienen de objetos Pedido creados dentro de esta prueba.
        order_ids = ','.join(str(int(order_id)) for order_id in created_order_ids)
        with engine.connect() as conn:
            conn.execute(text(f"""
                DELETE FROM outbox_eventos
                WHERE agregado_tipo = 'pedido'
                  AND CAST(agregado_id AS UNSIGNED) IN ({order_ids})
                  AND estado IN ('pendiente', 'error')
            """))
            conn.commit()
        deadline = time.time() + 5
        while time.time() < deadline:
            with engine.connect() as conn:
                processing = conn.execute(text(f"""
                    SELECT COUNT(*) FROM outbox_eventos
                    WHERE agregado_tipo = 'pedido'
                      AND CAST(agregado_id AS UNSIGNED) IN ({order_ids})
                      AND estado = 'procesando'
                """)).scalar_one()
            if not processing:
                break
            time.sleep(0.05)
        with engine.connect() as conn:
            conn.execute(text(f"""
                DELETE FROM outbox_eventos
                WHERE agregado_tipo = 'pedido'
                  AND CAST(agregado_id AS UNSIGNED) IN ({order_ids})
            """))
            conn.execute(text(f"DELETE FROM movimientos_inventario WHERE pedido_id IN ({order_ids})"))
            conn.execute(text(f"DELETE FROM pagos WHERE pedido_id IN ({order_ids})"))
            conn.execute(text(f"DELETE FROM pedido_lineas WHERE pedido_id IN ({order_ids})"))
            conn.execute(text(f"DELETE FROM pedidos WHERE id IN ({order_ids})"))
            conn.commit()

    with engine.connect() as conn:
        conn.execute(
            text("""
                DELETE FROM inventario_saldos_historial
                WHERE inventario_id = :inventory_id AND id > :original_max_id
            """),
            {
                'inventory_id': inventory_id,
                'original_max_id': original_max_balance_id,
            },
        )
        conn.execute(
            text("""
                UPDATE inventario_saldos_historial
                SET vigente_hasta = NULL,
                    cantidad_disponible = :stock,
                    cantidad_reservada = :reserved
                WHERE id = :original_id
            """),
            {
                'stock': original_stock,
                'reserved': original_reserved,
                'original_id': original_balance_id,
            },
        )
        conn.execute(
            text("""
                UPDATE inventario
                SET cantidad_disponible = :stock,
                    cantidad_reservada = :reserved
                WHERE oferta_id = :oid AND bodega = 'principal'
            """),
            {
                'stock': original_stock,
                'reserved': original_reserved,
                'oid': OFERTA_TEST_ID,
            },
        )
        conn.commit()
    mongo_products.update_one(
        {'_id': ObjectId(producto_ref)},
        {'$set': {
            'stock': original_projection.get('stock', original_stock),
            'disponible': original_projection.get('disponible', original_stock > 0),
        }},
    )
    mongo_client.close()


def test_checkout_exitoso(reset_stock):
    """Checkout normal con stock suficiente debe crear un pedido."""
    db: Session = TestSession()
    try:
        pedido = procesar_checkout(
            db,
            usuario_id=USUARIO_COMPRADOR_ID,
            direccion_id=DIRECCION_ID,
            metodo_pago_id=METODO_PAGO_ID,
            items=[CheckoutItem(oferta_id=OFERTA_TEST_ID, cantidad=2)],
        )
        reset_stock.append(pedido.id)
        assert pedido.id is not None
        assert pedido.estado == 'confirmado'
        assert float(pedido.total) > 0

        # Verificar que el stock disminuyó
        from sqlalchemy import text as t
        stock = db.execute(
            t("SELECT cantidad_disponible FROM inventario WHERE oferta_id=:oid AND bodega='principal'"),
            {'oid': OFERTA_TEST_ID}
        ).scalar()
        assert stock == 28  # 30 - 2
    finally:
        db.close()


def test_checkout_por_oferta_crea_subpedido_y_snapshots(reset_stock):
    """El contrato nuevo congela oferta, vendedor, SKU y dirección."""
    db: Session = TestSession()
    try:
        oferta_id = OFERTA_TEST_ID
        pedido = procesar_checkout(
            db,
            usuario_id=USUARIO_COMPRADOR_ID,
            direccion_id=DIRECCION_ID,
            metodo_pago_id=METODO_PAGO_ID,
            items=[CheckoutItem(oferta_id=oferta_id, cantidad=1)],
        )
        reset_stock.append(pedido.id)
        row = db.execute(text("""
            SELECT pl.oferta_id, pl.pedido_vendedor_id, pl.sku_snapshot,
                   pl.vendedor_nombre_snapshot, pd.receptor_nombre
            FROM pedido_lineas pl
            JOIN pedido_direcciones pd ON pd.pedido_id = pl.pedido_id
            WHERE pl.pedido_id = :pedido_id
        """), {'pedido_id': pedido.id}).mappings().one()
        assert row['oferta_id'] == oferta_id
        assert row['pedido_vendedor_id'] is not None
        assert row['sku_snapshot']
        assert row['vendedor_nombre_snapshot']
        assert row['receptor_nombre']
        event = db.execute(text("""
            SELECT estado, tipo_evento, producto_ref
            FROM outbox_eventos
            WHERE agregado_tipo = 'pedido' AND agregado_id = :pedido_id
        """), {'pedido_id': str(pedido.id)}).mappings().one()
        assert event['estado'] in {'pendiente', 'procesando', 'procesado'}
        assert event['tipo_evento'] == 'inventario.actualizado'
        assert event['producto_ref']
        movimiento_inventario = db.execute(text("""
            SELECT inventario_id FROM movimientos_inventario
            WHERE pedido_id = :pedido_id
        """), {'pedido_id': pedido.id}).scalar_one()
        inventario_id = db.execute(text("""
            SELECT id FROM inventario
            WHERE oferta_id = :oferta_id AND bodega = 'principal'
        """), {'oferta_id': oferta_id}).scalar_one()
        assert movimiento_inventario == inventario_id
    finally:
        db.close()


def test_checkout_sin_stock():
    """Checkout con cantidad mayor al stock disponible debe lanzar CheckoutError."""
    db: Session = TestSession()
    try:
        with pytest.raises(CheckoutError) as exc_info:
            procesar_checkout(
                db,
                usuario_id=USUARIO_COMPRADOR_ID,
                direccion_id=DIRECCION_ID,
                metodo_pago_id=METODO_PAGO_ID,
                items=[CheckoutItem(oferta_id=OFERTA_TEST_ID, cantidad=999)],
            )
        assert exc_info.value.code == 'INSUFFICIENT_STOCK'
    finally:
        db.close()


def test_checkout_carrito_vacio():
    """Checkout sin items debe lanzar CheckoutError."""
    db: Session = TestSession()
    try:
        with pytest.raises(CheckoutError) as exc_info:
            procesar_checkout(
                db,
                usuario_id=USUARIO_COMPRADOR_ID,
                direccion_id=DIRECCION_ID,
                metodo_pago_id=METODO_PAGO_ID,
                items=[],
            )
        assert exc_info.value.code == 'EMPTY_CART'
    finally:
        db.close()


def test_checkout_exige_confirmar_precio_cambiado():
    """El snapshot Redis no sustituye al precio vigente y exige confirmación."""
    db: Session = TestSession()
    try:
        precio_actual = db.execute(
            text('SELECT precio_actual FROM ofertas WHERE id = :oid'),
            {'oid': OFERTA_TEST_ID},
        ).scalar_one()
        with pytest.raises(CheckoutError) as exc_info:
            procesar_checkout(
                db,
                usuario_id=USUARIO_COMPRADOR_ID,
                direccion_id=DIRECCION_ID,
                metodo_pago_id=METODO_PAGO_ID,
                items=[CheckoutItem(oferta_id=OFERTA_TEST_ID, cantidad=1)],
                precios_esperados={OFERTA_TEST_ID: precio_actual - 1},
            )
        assert exc_info.value.code == 'PRICE_CHANGED'
        db.rollback()
    finally:
        db.close()


def test_checkout_rechaza_confirmacion_de_precio_que_volvio_a_cambiar():
    """Una confirmación vieja no acepta silenciosamente un segundo cambio."""
    db: Session = TestSession()
    try:
        precio_actual = db.execute(
            text('SELECT precio_actual FROM ofertas WHERE id = :oid'),
            {'oid': OFERTA_TEST_ID},
        ).scalar_one()
        with pytest.raises(CheckoutError) as exc_info:
            procesar_checkout(
                db,
                usuario_id=USUARIO_COMPRADOR_ID,
                direccion_id=DIRECCION_ID,
                metodo_pago_id=METODO_PAGO_ID,
                items=[CheckoutItem(oferta_id=OFERTA_TEST_ID, cantidad=1)],
                precios_esperados={OFERTA_TEST_ID: precio_actual - 2},
                confirmar_cambios_precio=True,
                precios_confirmados={OFERTA_TEST_ID: precio_actual - 1},
            )
        assert exc_info.value.code == 'PRICE_CHANGED'
        db.rollback()
    finally:
        db.close()


def test_checkout_acepta_precio_actual_confirmado(reset_stock):
    """Tras mostrar el valor vigente, la segunda confirmación puede comprar."""
    db: Session = TestSession()
    try:
        precio_actual = db.execute(
            text('SELECT precio_actual FROM ofertas WHERE id = :oid'),
            {'oid': OFERTA_TEST_ID},
        ).scalar_one()
        pedido = procesar_checkout(
            db,
            usuario_id=USUARIO_COMPRADOR_ID,
            direccion_id=DIRECCION_ID,
            metodo_pago_id=METODO_PAGO_ID,
            items=[CheckoutItem(oferta_id=OFERTA_TEST_ID, cantidad=1)],
            precios_esperados={OFERTA_TEST_ID: precio_actual - 1},
            confirmar_cambios_precio=True,
            precios_confirmados={OFERTA_TEST_ID: precio_actual},
        )
        reset_stock.append(pedido.id)
        assert pedido.total == precio_actual
    finally:
        db.close()


def test_checkout_flash_convierte_reserva_y_descuenta_pool(reset_stock):
    """La compra flash usa el precio promocional y consume el cupo reservado."""
    db: Session = TestSession()
    promotion = None
    reservation = None
    try:
        seller_user_id = db.execute(
            text("""
                SELECT v.usuario_id
                FROM ofertas o
                JOIN vendedores v ON v.id = o.vendedor_id
                WHERE o.id = :offer_id
            """),
            {'offer_id': OFERTA_TEST_ID},
        ).scalar_one()
        now = utc_now()
        promotion = PromocionFlash(
            oferta_id=OFERTA_TEST_ID,
            creado_por=seller_user_id,
            precio_promocional=Decimal('1.00'),
            unidades_totales=1,
            unidades_vendidas=0,
            max_por_usuario=1,
            segundos_reserva=300,
            inicia_en=now - timedelta(seconds=5),
            finaliza_en=now + timedelta(minutes=10),
            estado='activa',
        )
        db.add(promotion)
        db.flush()
        reservation = ReservaFlash(
            token=str(uuid4()),
            promocion_id=promotion.id,
            usuario_id=USUARIO_COMPRADOR_ID,
            cantidad=1,
            precio_unitario=Decimal('1.00'),
            estado='reservada',
            expira_en=now + timedelta(minutes=5),
        )
        db.add(reservation)
        db.execute(
            text("""
                UPDATE inventario
                SET cantidad_reservada = cantidad_reservada + 1
                WHERE oferta_id = :offer_id AND bodega = 'principal'
            """),
            {'offer_id': OFERTA_TEST_ID},
        )
        db.commit()

        pedido = procesar_checkout(
            db,
            usuario_id=USUARIO_COMPRADOR_ID,
            direccion_id=DIRECCION_ID,
            metodo_pago_id=METODO_PAGO_ID,
            items=[CheckoutItem(oferta_id=OFERTA_TEST_ID, cantidad=1)],
            promociones_flash={
                OFERTA_TEST_ID: {
                    'promocion_id': promotion.id,
                    'token': reservation.token,
                }
            },
        )
        reset_stock.append(pedido.id)

        db.refresh(promotion)
        db.refresh(reservation)
        inventory = db.execute(
            text("""
                SELECT cantidad_disponible, cantidad_reservada
                FROM inventario
                WHERE oferta_id = :offer_id AND bodega = 'principal'
            """),
            {'offer_id': OFERTA_TEST_ID},
        ).one()
        assert pedido.total == Decimal('1.00')
        assert promotion.unidades_vendidas == 1
        assert promotion.estado == 'finalizada'
        assert reservation.estado == 'convertida'
        assert reservation.pedido_id == pedido.id
        assert inventory.cantidad_disponible == 29
        assert inventory.cantidad_reservada == 0
    finally:
        db.rollback()
        if reservation is not None:
            db.delete(reservation)
            db.commit()
        if promotion is not None:
            db.delete(promotion)
            db.commit()
        db.close()


def test_concurrencia_ultima_unidad(reset_stock):
    """
    Dos hilos compran la última unidad al mismo tiempo.
    Solo uno debe tener éxito; el otro debe recibir CheckoutError INSUFFICIENT_STOCK.

    Este test demuestra que SELECT FOR UPDATE previene la sobreventa.
    """
    # Reducir el stock a 1 unidad
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE inventario SET cantidad_disponible = 1 WHERE oferta_id = :oid AND bodega = 'principal'"),
            {'oid': OFERTA_TEST_ID}
        )
        conn.commit()

    resultados = []
    errores = []
    barrera = threading.Barrier(2)  # Sincroniza ambos hilos para que empiecen simultáneamente

    def comprar():
        db = TestSession()
        try:
            barrera.wait()  # Espera a que ambos hilos estén listos
            pedido = procesar_checkout(
                db,
                usuario_id=USUARIO_COMPRADOR_ID,
                direccion_id=DIRECCION_ID,
                metodo_pago_id=METODO_PAGO_ID,
                items=[CheckoutItem(oferta_id=OFERTA_TEST_ID, cantidad=1)],
            )
            resultados.append(pedido.id)
        except CheckoutError as e:
            errores.append(e.code)
        except Exception as e:
            errores.append(str(e))
        finally:
            db.close()

    hilo1 = threading.Thread(target=comprar)
    hilo2 = threading.Thread(target=comprar)
    hilo1.start()
    hilo2.start()
    hilo1.join()
    hilo2.join()

    # Exactamente uno tuvo éxito y el otro falló
    assert len(resultados) == 1, f'Se esperaba 1 éxito, hubo {len(resultados)}'
    reset_stock.extend(resultados)
    assert len(errores) == 1, f'Se esperaba 1 error, hubo {len(errores)}'
    assert errores[0] == 'INSUFFICIENT_STOCK', f'Error inesperado: {errores[0]}'

    # El stock debe quedar en 0
    with engine.connect() as conn:
        stock = conn.execute(
            text("SELECT cantidad_disponible FROM inventario WHERE oferta_id=:oid AND bodega='principal'"),
            {'oid': OFERTA_TEST_ID}
        ).scalar()
    assert stock == 0, f'Stock esperado: 0, real: {stock}'
