"""Pruebas de atomicidad, aislamiento y expiración del carrito Redis."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import time

import pytest
import redis

from app.core.config import settings
from app.services import redis_cart_service as carts


USUARIO_A = 9_900_001
USUARIO_B = 9_900_002
OFERTA = 123_456


@pytest.fixture
def redis_client():
    client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    client.ping()
    client.delete(carts._key(USUARIO_A), carts._key(USUARIO_B))
    yield client
    client.delete(carts._key(USUARIO_A), carts._key(USUARIO_B))


def test_crud_renueva_ttl_y_aisla_usuarios(redis_client):
    cantidad = carts.agregar_item(
        redis_client, USUARIO_A, OFERTA, 2, Decimal('99.90'), 'abc123'
    )
    assert cantidad == 2
    assert carts.obtener_carrito(redis_client, USUARIO_A)[0]['cantidad'] == 2
    assert carts.obtener_carrito(redis_client, USUARIO_B) == []
    assert 0 < carts.ttl_restante(redis_client, USUARIO_A) <= settings.REDIS_CART_TTL

    assert carts.actualizar_cantidad(redis_client, USUARIO_A, OFERTA, 4)
    assert carts.obtener_carrito(redis_client, USUARIO_A)[0]['cantidad'] == 4
    assert carts.eliminar_item(redis_client, USUARIO_A, OFERTA)
    assert carts.ttl_restante(redis_client, USUARIO_A) == -2


def test_cien_incrementos_concurrentes_no_se_pierden(redis_client):
    def agregar_una():
        return carts.agregar_item(
            redis_client, USUARIO_A, OFERTA, 1, Decimal('10.00'), 'abc123'
        )

    with ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(lambda _: agregar_una(), range(100)))

    [item] = carts.obtener_carrito(redis_client, USUARIO_A)
    assert item['cantidad'] == 100


def test_carrito_expira_por_inactividad(redis_client, monkeypatch):
    monkeypatch.setattr(carts, '_TTL', 1)
    carts.agregar_item(
        redis_client, USUARIO_A, OFERTA, 1, Decimal('10.00'), 'abc123'
    )
    assert carts.carrito_existe(redis_client, USUARIO_A)
    time.sleep(1.2)
    assert not carts.carrito_existe(redis_client, USUARIO_A)
