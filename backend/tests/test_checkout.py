"""
Pruebas del servicio de checkout:
  - checkout exitoso
  - checkout sin stock suficiente
  - concurrencia: dos hilos compran la última unidad → solo uno tiene éxito
"""
import threading
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.services.checkout_service import procesar_checkout, CheckoutError
from app.schemas.checkout import CheckoutItem

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
PRODUCTO_TEST_ID     = 65  # Mouse Logitech MX Master 3 — stock inicial: 30


@pytest.fixture(autouse=True)
def reset_stock():
    """Restaura el stock antes de cada prueba para que sean independientes."""
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE inventario SET cantidad_disponible = 30 WHERE producto_id = :pid AND bodega = 'principal'"),
            {'pid': PRODUCTO_TEST_ID}
        )
        conn.commit()
    yield
    # Limpiar pedidos creados en las pruebas para no contaminar el seed
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM movimientos_inventario WHERE motivo = 'venta' AND pedido_id > 30"))
        conn.execute(text("DELETE FROM pagos WHERE pedido_id > 30"))
        conn.execute(text("DELETE FROM pedido_lineas WHERE pedido_id > 30"))
        conn.execute(text("DELETE FROM pedidos WHERE id > 30"))
        conn.execute(
            text("UPDATE inventario SET cantidad_disponible = 30 WHERE producto_id = :pid AND bodega = 'principal'"),
            {'pid': PRODUCTO_TEST_ID}
        )
        conn.commit()


def test_checkout_exitoso():
    """Checkout normal con stock suficiente debe crear un pedido."""
    db: Session = TestSession()
    try:
        pedido = procesar_checkout(
            db,
            usuario_id=USUARIO_COMPRADOR_ID,
            direccion_id=DIRECCION_ID,
            metodo_pago_id=METODO_PAGO_ID,
            items=[CheckoutItem(producto_id=PRODUCTO_TEST_ID, cantidad=2)],
        )
        assert pedido.id is not None
        assert pedido.estado == 'confirmado'
        assert float(pedido.total) > 0

        # Verificar que el stock disminuyó
        from sqlalchemy import text as t
        stock = db.execute(
            t("SELECT cantidad_disponible FROM inventario WHERE producto_id=:pid AND bodega='principal'"),
            {'pid': PRODUCTO_TEST_ID}
        ).scalar()
        assert stock == 28  # 30 - 2
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
                items=[CheckoutItem(producto_id=PRODUCTO_TEST_ID, cantidad=999)],
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


def test_concurrencia_ultima_unidad():
    """
    Dos hilos compran la última unidad al mismo tiempo.
    Solo uno debe tener éxito; el otro debe recibir CheckoutError INSUFFICIENT_STOCK.

    Este test demuestra que SELECT FOR UPDATE previene la sobreventa.
    """
    # Reducir el stock a 1 unidad
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE inventario SET cantidad_disponible = 1 WHERE producto_id = :pid AND bodega = 'principal'"),
            {'pid': PRODUCTO_TEST_ID}
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
                items=[CheckoutItem(producto_id=PRODUCTO_TEST_ID, cantidad=1)],
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
    assert len(errores) == 1, f'Se esperaba 1 error, hubo {len(errores)}'
    assert errores[0] == 'INSUFFICIENT_STOCK', f'Error inesperado: {errores[0]}'

    # El stock debe quedar en 0
    with engine.connect() as conn:
        stock = conn.execute(
            text("SELECT cantidad_disponible FROM inventario WHERE producto_id=:pid AND bodega='principal'"),
            {'pid': PRODUCTO_TEST_ID}
        ).scalar()
    assert stock == 0, f'Stock esperado: 0, real: {stock}'
