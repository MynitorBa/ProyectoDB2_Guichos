"""Evidencia de atomicidad y expiración para ventas flash en Redis."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
import redis

from app.core.config import settings
from app.core.time import utc_now
from app.services import flash_sale_service as flash


PROMOTION_ID = 9_800_001


@pytest.fixture
def redis_client():
    client = redis.Redis(
        host=settings.REDIS_HOST, port=settings.REDIS_PORT,
        decode_responses=True, socket_connect_timeout=2, socket_timeout=2,
    )
    client.ping()
    flash.eliminar(client, PROMOTION_ID)
    yield client
    flash.eliminar(client, PROMOTION_ID)


def init(client, units=10):
    flash.inicializar(
        client, promocion_id=PROMOTION_ID, unidades=units,
        max_por_usuario=1, inicia_ts=1_000, finaliza_ts=10_000,
        precio=Decimal('25.00'),
    )


def test_cien_compradores_compiten_por_diez_unidades(redis_client):
    init(redis_client, 10)

    def reserve(user_id):
        return flash.reservar(
            redis_client, promocion_id=PROMOTION_ID, usuario_id=user_id,
            cantidad=1, token=str(uuid4()), ahora_ts=2_000,
            segundos_reserva=300,
        )

    with ThreadPoolExecutor(max_workers=25) as pool:
        results = list(pool.map(reserve, range(1, 101)))

    winners = [result for result in results if result['codigo'] == 1]
    sold_out = [result for result in results if result['codigo'] == 0]
    assert len(winners) == 10
    assert len(sold_out) == 90
    assert len({winner['token'] for winner in winners}) == 10
    assert flash.obtener_estado(redis_client, PROMOTION_ID)['disponibles'] == 0


def test_reintento_del_mismo_usuario_es_idempotente(redis_client):
    init(redis_client, 2)
    first = flash.reservar(
        redis_client, promocion_id=PROMOTION_ID, usuario_id=7, cantidad=1,
        token=str(uuid4()), ahora_ts=2_000, segundos_reserva=300,
    )
    retry = flash.reservar(
        redis_client, promocion_id=PROMOTION_ID, usuario_id=7, cantidad=1,
        token=str(uuid4()), ahora_ts=2_001, segundos_reserva=300,
    )
    assert first['codigo'] == 1
    assert retry['codigo'] == 2
    assert retry['token'] == first['token']
    assert retry['disponibles'] == 1


def test_reserva_vencida_devuelve_cupo(redis_client):
    init(redis_client, 1)
    flash.reservar(
        redis_client, promocion_id=PROMOTION_ID, usuario_id=7, cantidad=1,
        token=str(uuid4()), ahora_ts=2_000, segundos_reserva=1,
    )
    cleaned = flash.limpiar_expiradas(redis_client, PROMOTION_ID, 2_002)
    assert cleaned == {'liberadas': 1, 'disponibles': 1}


def test_reserva_nunca_sobrevive_al_final_de_la_promocion(redis_client):
    flash.inicializar(
        redis_client, promocion_id=PROMOTION_ID, unidades=1,
        max_por_usuario=1, inicia_ts=1_000, finaliza_ts=2_180,
        precio=Decimal('25.00'),
    )
    reservation = flash.reservar(
        redis_client, promocion_id=PROMOTION_ID, usuario_id=7, cantidad=1,
        token=str(uuid4()), ahora_ts=2_000, segundos_reserva=300,
    )
    assert reservation['codigo'] == 1
    assert reservation['expira_ts'] == 2_180


def test_redis_se_reconstruye_desde_el_estado_durable(redis_client):
    now = utc_now()
    promotion = SimpleNamespace(
        id=PROMOTION_ID,
        unidades_totales=5,
        unidades_vendidas=1,
        max_por_usuario=1,
        inicia_en=now - timedelta(minutes=1),
        finaliza_en=now + timedelta(minutes=10),
        precio_promocional=Decimal('25.00'),
    )
    reservation = SimpleNamespace(
        usuario_id=7,
        token=str(uuid4()),
        cantidad=1,
        estado='reservada',
        expira_en=now + timedelta(minutes=5),
    )

    assert flash.rehidratar_si_falta(redis_client, promotion, [reservation]) is True
    state = flash.obtener_estado(redis_client, PROMOTION_ID)
    restored = flash.obtener_reserva(redis_client, PROMOTION_ID, 7)
    assert state['disponibles'] == 3
    assert state['vendidas'] == 1
    assert restored['token'] == reservation.token
