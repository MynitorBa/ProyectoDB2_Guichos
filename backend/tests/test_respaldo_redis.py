"""Plan B de Redis: el carrito y las ofertas flash siguen funcionando sobre MySQL.

Redis «caído» es un cliente real apuntando a un puerto sin servidor, con
tiempos de espera cortos: las llamadas fallan igual que con el contenedor
detenido, pero sin detener el Redis que usan las demás pruebas.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.core import salud
from app.core.db_redis import get_redis
from app.core.time import utc_now
from app.main import app
from app.models.promocion_flash import PromocionFlash, ReservaFlash
from app.services import carrito_respaldo_service as respaldo
from app.services import flash_sale_service as flash
from app.services import redis_cart_service as rcs
from app.services.flash_sale_worker import resincronizar_pendientes
from tests.test_checkout import (  # noqa: F401  (reset_stock limpia los pedidos creados)
    DIRECCION_ID, METODO_PAGO_ID, OFERTA_TEST_ID, TestSession, USUARIO_COMPRADOR_ID, reset_stock,
)

USUARIO = USUARIO_COMPRADOR_ID


def _redis_caido() -> redis.Redis:
    return redis.Redis(host='127.0.0.1', port=1, decode_responses=True,
                       socket_connect_timeout=0.2, socket_timeout=0.2)


def _respaldo_items(usuario_id: int) -> dict[int, dict]:
    import json
    with TestSession() as db:
        filas = db.execute(text(
            'SELECT oferta_id, datos FROM carritos_respaldo_items WHERE usuario_id = :u'
        ), {'u': usuario_id}).all()
    return {o: (json.loads(d) if isinstance(d, str) else d) for o, d in filas}


def _pendiente(usuario_id: int) -> bool | None:
    with TestSession() as db:
        valor = db.execute(text(
            'SELECT pendiente_redis FROM carritos_respaldo WHERE usuario_id = :u'
        ), {'u': usuario_id}).scalar()
    return None if valor is None else bool(valor)


@pytest.fixture
def carrito_limpio():
    """Respalda el carrito real del comprador y deja ambos almacenes vacíos."""
    r = get_redis()
    clave = rcs._key(USUARIO)
    guardado, ttl = r.hgetall(clave), r.ttl(clave)

    def limpiar():
        r.delete(clave)
        with TestSession() as db:
            db.execute(text('DELETE FROM carritos_respaldo WHERE usuario_id = :u'), {'u': USUARIO})
            db.commit()

    limpiar()
    yield r
    limpiar()
    if guardado:
        r.hset(clave, mapping=guardado)
        if ttl and ttl > 0:
            r.expire(clave, ttl)


# ── Carrito ───────────────────────────────────────────────────────────────────

def test_con_redis_arriba_cada_cambio_se_copia_en_mysql(carrito_limpio):
    rcs.agregar_item(carrito_limpio, USUARIO, 11, 2, Decimal('10.00'), None)
    rcs.agregar_item(carrito_limpio, USUARIO, 12, 1, Decimal('5.00'), None)
    rcs.eliminar_item(carrito_limpio, USUARIO, 12)

    assert _respaldo_items(USUARIO) == {11: {'cantidad': 2, 'precio_al_agregar': '10.00', 'producto_ref': None}}
    assert _pendiente(USUARIO) is False


def test_sin_redis_el_carrito_funciona_sobre_mysql(carrito_limpio):
    caido = _redis_caido()
    assert rcs.agregar_item(caido, USUARIO, 11, 2, Decimal('10.00'), 'abc') == 2
    assert rcs.agregar_item(caido, USUARIO, 11, 1, Decimal('10.00'), 'abc') == 3
    assert rcs.actualizar_cantidad(caido, USUARIO, 11, 5)
    assert not rcs.actualizar_cantidad(caido, USUARIO, 99, 1)
    rcs.agregar_item(caido, USUARIO, 12, 1, Decimal('5.00'), None)
    assert rcs.eliminar_item(caido, USUARIO, 12)

    [item] = rcs.obtener_carrito(caido, USUARIO)
    assert item['oferta_id'] == 11 and item['cantidad'] == 5
    assert 0 < rcs.ttl_restante(caido, USUARIO) <= respaldo.TTL
    assert _pendiente(USUARIO) is True
    # Tras las primeras fallas el circuito se abre y ya no se espera a Redis.
    assert not salud.disponible('redis')
    assert rcs.en_respaldo()


def test_al_volver_redis_el_carrito_se_reconstruye_desde_mysql(carrito_limpio):
    # Redis conserva una versión vieja del carrito...
    rcs.agregar_item(carrito_limpio, USUARIO, 11, 1, Decimal('10.00'), None)
    # ...y mientras estaba caído el usuario siguió comprando sobre MySQL.
    caido = _redis_caido()
    rcs.agregar_item(caido, USUARIO, 11, 3, Decimal('10.00'), None)
    rcs.agregar_item(caido, USUARIO, 13, 1, Decimal('7.00'), None)
    salud.reiniciar()  # Redis volvió

    items = {i['oferta_id']: i['cantidad'] for i in rcs.obtener_carrito(carrito_limpio, USUARIO)}

    assert items == {11: 4, 13: 1}
    assert set(carrito_limpio.hgetall(rcs._key(USUARIO))) == {'11', '13'}
    assert carrito_limpio.ttl(rcs._key(USUARIO)) > 0
    assert _pendiente(USUARIO) is False


def test_vaciar_sin_redis_tambien_vacia_redis_al_volver(carrito_limpio):
    rcs.agregar_item(carrito_limpio, USUARIO, 11, 1, Decimal('10.00'), None)
    rcs.vaciar_carrito(_redis_caido(), USUARIO)
    salud.reiniciar()
    assert rcs.obtener_carrito(carrito_limpio, USUARIO) == []
    assert not carrito_limpio.exists(rcs._key(USUARIO))


def test_agregados_concurrentes_sobre_mysql_no_se_pierden(carrito_limpio):
    caido = _redis_caido()
    salud.registrar_falla('redis', 'caído', confirmada=True)  # directo al respaldo
    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(lambda _: rcs.agregar_item(caido, USUARIO, 11, 1, Decimal('1.00'), None), range(30)))
    [item] = rcs.obtener_carrito(caido, USUARIO)
    assert item['cantidad'] == 30


def test_si_tambien_falla_mysql_se_responde_carrito_no_disponible(carrito_limpio, monkeypatch):
    def mysql_caido(*_args, **_kwargs):
        raise OperationalError('SELECT 1', {}, Exception('MySQL caído'))

    monkeypatch.setattr(respaldo, 'leer', mysql_caido)
    with pytest.raises(rcs.CarritoNoDisponible) as error:
        rcs.obtener_carrito(_redis_caido(), USUARIO)
    assert isinstance(error.value, redis.RedisError)  # los routers ya lo traducen a 503


# ── Endpoints con Redis caído ─────────────────────────────────────────────────

@pytest.fixture
def cliente_sin_redis(carrito_limpio):
    cliente = TestClient(app)
    token = cliente.post('/api/v1/auth/login', json={
        'email': 'comprador1@gmail.com', 'password': 'password123',
    }).json()['access_token']
    cliente.headers['Authorization'] = f'Bearer {token}'
    app.dependency_overrides[get_redis] = _redis_caido
    yield cliente
    app.dependency_overrides.pop(get_redis, None)


def test_api_carrito_y_compra_completa_sin_redis(cliente_sin_redis, reset_stock):
    agregado = cliente_sin_redis.post('/api/v1/cart/items', json={'oferta_id': OFERTA_TEST_ID, 'cantidad': 1})
    assert agregado.status_code == 201, agregado.text

    carrito = cliente_sin_redis.get('/api/v1/cart/').json()
    assert [i['oferta_id'] for i in carrito['items']] == [OFERTA_TEST_ID]

    compra = cliente_sin_redis.post(
        '/api/v1/orders/checkout',
        json={'direccion_id': DIRECCION_ID, 'metodo_pago_id': METODO_PAGO_ID},
        headers={'Idempotency-Key': str(uuid4())},
    )
    assert compra.status_code == 201, compra.text
    reset_stock.append(compra.json()['pedido_id'])
    # Lo comprado sale del carrito en la misma transacción que confirma el pedido.
    assert OFERTA_TEST_ID not in _respaldo_items(USUARIO)
    assert cliente_sin_redis.get('/api/v1/cart/').json()['items'] == []


# ── Ventas flash sobre MySQL ──────────────────────────────────────────────────

@pytest.fixture
def promocion_mysql():
    """Promoción activa creada directamente en MySQL, con 3 unidades."""
    with TestSession() as db:
        oferta_id = db.execute(text("""
            SELECT o.id FROM ofertas o
            WHERE o.estado = 'activa' AND NOT EXISTS (
                SELECT 1 FROM promociones_flash p
                WHERE p.oferta_id = o.id AND p.estado IN ('programada', 'activa'))
            ORDER BY o.id LIMIT 1
        """)).scalar_one()
        usuarios = [fila[0] for fila in db.execute(text('SELECT id FROM usuarios ORDER BY id LIMIT 10'))]
        ahora = utc_now()
        promo = PromocionFlash(
            oferta_id=oferta_id, creado_por=usuarios[0], precio_promocional=Decimal('1.00'),
            unidades_totales=3, unidades_vendidas=0, max_por_usuario=1, segundos_reserva=300,
            inicia_en=ahora - timedelta(minutes=1), finaliza_en=ahora + timedelta(hours=1), estado='activa',
        )
        db.add(promo)
        db.commit()
        promo_id = promo.id
    yield promo_id, usuarios
    get_redis().delete(*flash._keys(promo_id))
    with TestSession() as db:
        db.execute(text('DELETE FROM flash_resincronizar WHERE promocion_id = :p'), {'p': promo_id})
        db.execute(text('DELETE FROM reservas_flash WHERE promocion_id = :p'), {'p': promo_id})
        db.execute(text('DELETE FROM promociones_flash WHERE id = :p'), {'p': promo_id})
        db.commit()


def test_diez_compradores_compiten_por_tres_unidades_en_mysql(promocion_mysql):
    promo_id, usuarios = promocion_mysql

    def reservar(usuario_id):
        with TestSession() as db:
            return flash.reservar_en_mysql(
                db, promocion_id=promo_id, usuario_id=usuario_id, cantidad=1, token=str(uuid4()),
            )['codigo']

    with ThreadPoolExecutor(max_workers=10) as pool:
        codigos = list(pool.map(reservar, usuarios))

    assert codigos.count(1) == 3
    assert set(codigos) == {0, 1}
    with TestSession() as db:
        assert flash.disponibles_mysql(db, db.get(PromocionFlash, promo_id)) == 0
        assert flash.pendiente_resincronizar(db, promo_id)


def test_el_mismo_comprador_recupera_su_reserva(promocion_mysql):
    promo_id, usuarios = promocion_mysql
    with TestSession() as db:
        primera = flash.reservar_en_mysql(db, promocion_id=promo_id, usuario_id=usuarios[0], cantidad=1, token='t-1')
        segunda = flash.reservar_en_mysql(db, promocion_id=promo_id, usuario_id=usuarios[0], cantidad=1, token='t-2')
        excedida = flash.reservar_en_mysql(db, promocion_id=promo_id, usuario_id=usuarios[1], cantidad=2, token='t-3')
    assert primera['codigo'] == 1 and segunda['codigo'] == 2 and segunda['token'] == 't-1'
    assert excedida['codigo'] == -2


def test_al_volver_redis_la_promocion_se_reconstruye_con_las_reservas_de_mysql(promocion_mysql):
    promo_id, usuarios = promocion_mysql
    r = get_redis()
    with TestSession() as db:
        promo = db.get(PromocionFlash, promo_id)
        flash.rehidratar_si_falta(r, promo, [])  # Redis tenía el estado viejo: 3 libres
        flash.reservar_en_mysql(db, promocion_id=promo_id, usuario_id=usuarios[0], cantidad=1, token='t-a')

        assert resincronizar_pendientes(db, r) == 1
        reservas = db.query(ReservaFlash).filter_by(promocion_id=promo_id, estado='reservada').all()
        flash.rehidratar_si_falta(r, db.get(PromocionFlash, promo_id), reservas)

        assert flash.obtener_estado(r, promo_id)['disponibles'] == 2
        assert flash.obtener_reserva(r, promo_id, usuarios[0])['token'] == 't-a'
        assert not flash.pendiente_resincronizar(db, promo_id)


def test_reserva_vigente_usa_mysql_sin_redis(promocion_mysql):
    promo_id, usuarios = promocion_mysql
    with TestSession() as db:
        flash.reservar_en_mysql(db, promocion_id=promo_id, usuario_id=usuarios[0], cantidad=1, token='t-v')
        reserva = flash.reserva_vigente(_redis_caido(), db, promo_id, usuarios[0])
    assert reserva['token'] == 't-v' and reserva['cantidad'] == 1
