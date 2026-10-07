"""Outbox por destino: rutas, proyecciones por estado, aislamiento y reintentos."""

from datetime import timedelta
from decimal import Decimal

import pytest
from bson import ObjectId
from sqlalchemy import text

from app.core.config import settings
from app.core.db_elastic import get_es
from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import SessionLocal
from app.core.db_neo4j import get_driver
from app.core.db_redis import get_redis
from app.models.outbox import OutboxEvento
from app.services import outbox_service as outbox
from app.services import redis_cart_service as rcs
from app.services.offer_service import listar_ofertas_por_referencias, proyeccion_oferta_principal

SKU_DELL = 'TECH-LAP-001'  # producto con varias ofertas de distintos vendedores
USUARIO_PRUEBA = 990_001   # clave de carrito exclusiva de esta prueba


@pytest.fixture
def eventos_creados():
    ids: list[str] = []
    yield ids
    with SessionLocal() as db:
        if ids:
            db.query(OutboxEvento).filter(OutboxEvento.id.in_(ids)).delete(synchronize_session=False)
            db.commit()
    outbox._pausas.clear()


@pytest.fixture(scope='module')
def ref_dell():
    return str(get_mongo_db().productos.find_one({'sku': SKU_DELL}, {'_id': 1})['_id'])


def _encolar(db, ids, **kwargs) -> list[OutboxEvento]:
    primero = outbox.enqueue_outbox(db, **kwargs)
    db.flush()
    filas = db.query(OutboxEvento).filter(
        OutboxEvento.tipo_evento == kwargs['tipo_evento'],
        OutboxEvento.agregado_id == str(kwargs['agregado_id']),
        OutboxEvento.secuencia >= primero.secuencia,
    ).order_by(OutboxEvento.secuencia).all()
    ids.extend(f.id for f in filas)
    return filas


def _procesar_hasta(ids: list[str], estados: set[str], intentos: int = 200) -> dict[str, str]:
    for _ in range(intentos):
        # Eventos ajenos a la prueba pueden fallar y pausar un destino; la pausa
        # es una optimización del worker, no parte de lo que se verifica aquí.
        outbox._pausas.clear()
        with SessionLocal() as db:
            actuales = dict(db.query(OutboxEvento.id, OutboxEvento.estado).filter(OutboxEvento.id.in_(ids)).all())
        if all(estado in estados for estado in actuales.values()):
            return actuales
        if not outbox.process_one():
            break
    with SessionLocal() as db:
        return dict(db.query(OutboxEvento.id, OutboxEvento.estado).filter(OutboxEvento.id.in_(ids)).all())


# ── Rutas ─────────────────────────────────────────────────────────────────────

def test_un_evento_crea_una_fila_por_destino_en_orden(eventos_creados, ref_dell):
    with SessionLocal() as db:
        filas = _encolar(
            db, eventos_creados, tipo_evento='inventario.actualizado', agregado_tipo='prueba',
            agregado_id='rutas-v2', producto_ref=ref_dell, payload={},
        )
        assert [f.destino for f in filas] == ['mongo', 'busqueda']
        assert filas[0].secuencia < filas[1].secuencia
        db.rollback()  # el rollback también descarta el evento: atomicidad con el negocio
        assert db.query(OutboxEvento).filter_by(agregado_id='rutas-v2').count() == 0
    assert outbox.destinos_de('evento.desconocido') == ('mongo',)
    assert outbox.destinos_de('grafo.compra_registrada') == ('neo4j',)


# ── MongoDB: proyección por estado (corrige la falla de la línea base) ────────

def test_proyeccion_mongo_usa_el_stock_total_y_no_el_delta_del_evento(eventos_creados, ref_dell):
    mongo = get_mongo_db()
    # Reproduce la divergencia de la línea base: stock de una sola oferta.
    mongo.productos.update_one({'_id': ObjectId(ref_dell)}, {'$set': {'stock': 9}})
    with SessionLocal() as db:
        _encolar(
            db, eventos_creados, tipo_evento='inventario.actualizado', agregado_tipo='prueba',
            agregado_id='estado-mongo', producto_ref=ref_dell,
            payload={'projection': {'stock': 9, 'disponible': True}},
            destinos=('mongo',),
        )
        db.commit()
        esperado = proyeccion_oferta_principal(db, ref_dell)
        ofertas = listar_ofertas_por_referencias(db, [ref_dell])[ref_dell]

    assert set(_procesar_hasta(eventos_creados, {'procesado'}).values()) == {'procesado'}
    doc = mongo.productos.find_one({'_id': ObjectId(ref_dell)})
    assert len(ofertas) > 1
    assert doc['stock'] == sum(o['stock'] for o in ofertas) == esperado['stock']
    assert doc['oferta_id'] == esperado['oferta_id']


def test_proyeccion_mongo_no_depende_del_orden(eventos_creados, ref_dell):
    with SessionLocal() as db:
        primero = _encolar(
            db, eventos_creados, tipo_evento='oferta.precio_actualizado', agregado_tipo='prueba',
            agregado_id='orden-a', producto_ref=ref_dell, payload={'projection': {'precio': 1.0}},
            destinos=('mongo',),
        )[0]
        segundo = _encolar(
            db, eventos_creados, tipo_evento='inventario.actualizado', agregado_tipo='prueba',
            agregado_id='orden-b', producto_ref=ref_dell, payload={'projection': {'stock': 0}},
            destinos=('mongo',),
        )[0]
        db.commit()
        outbox.project_event(segundo, db)
        outbox.project_event(primero, db)  # llega tarde y repetido
        outbox.project_event(primero, db)
        esperado = proyeccion_oferta_principal(db, ref_dell)
    doc = get_mongo_db().productos.find_one({'_id': ObjectId(ref_dell)})
    assert {k: doc[k] for k in esperado} == esperado


# ── Elasticsearch ─────────────────────────────────────────────────────────────

def test_destino_busqueda_reconstruye_el_documento_desde_mysql(eventos_creados, ref_dell):
    es = get_es()
    es.options(ignore_status=404).delete(index=settings.ES_INDEX_ALIAS, id=ref_dell, refresh=True)
    with SessionLocal() as db:
        _encolar(
            db, eventos_creados, tipo_evento='producto.catalogo_actualizado', agregado_tipo='prueba',
            agregado_id='busqueda-v2', producto_ref=ref_dell, payload={},
        )
        db.commit()
        ofertas = listar_ofertas_por_referencias(db, [ref_dell])[ref_dell]
    assert set(_procesar_hasta(eventos_creados, {'procesado'}).values()) == {'procesado'}
    documento = es.get(index=settings.ES_INDEX_ALIAS, id=ref_dell)['_source']
    assert documento['stock_total'] == sum(o['stock'] for o in ofertas)


def test_evento_de_pedido_reindexa_sus_productos(ref_dell):
    with SessionLocal() as db:
        pedido_id = db.execute(text(
            'SELECT pedido_id FROM pedido_lineas WHERE producto_ref = :ref ORDER BY pedido_id DESC LIMIT 1'
        ), {'ref': ref_dell}).scalar_one()
        evento = OutboxEvento(
            id='prueba-refs', tipo_evento='analytics.pedido_actualizado', destino='busqueda',
            agregado_tipo='pedido', agregado_id=str(pedido_id), producto_ref=None, payload={},
        )
        assert ref_dell in outbox._refs_del_evento(evento, db)


# ── Neo4j y Redis ─────────────────────────────────────────────────────────────

def test_destino_neo4j_registra_compras_de_forma_idempotente():
    with SessionLocal() as db:
        pedido_id = db.execute(text("""
            SELECT p.id FROM pedidos p JOIN pedido_lineas pl ON pl.pedido_id = p.id
            WHERE pl.producto_ref IS NOT NULL ORDER BY p.id DESC LIMIT 1
        """)).scalar_one()
        evento = OutboxEvento(
            id='prueba-neo4j', tipo_evento='grafo.compra_registrada', destino='neo4j',
            agregado_tipo='pedido', agregado_id=str(pedido_id), producto_ref=None, payload={},
        )
        outbox.project_event(evento, db)
        with get_driver().session() as s:
            primero = s.run('MATCH ()-[c:COMPRO {pedido_id: $id}]->() RETURN count(c) AS n', id=pedido_id).single()['n']
        outbox.project_event(evento, db)
        with get_driver().session() as s:
            segundo = s.run('MATCH ()-[c:COMPRO {pedido_id: $id}]->() RETURN count(c) AS n', id=pedido_id).single()['n']
    assert primero > 0
    assert segundo == primero


def test_destino_redis_retira_solo_lo_comprado():
    r = get_redis()
    r.delete(f'carrito:{USUARIO_PRUEBA}')
    try:
        rcs.agregar_item(r, USUARIO_PRUEBA, 1, 1, Decimal('10.00'), None)
        rcs.agregar_item(r, USUARIO_PRUEBA, 2, 1, Decimal('20.00'), None)
        evento = OutboxEvento(
            id='prueba-redis', tipo_evento='carrito.limpiar', destino='redis',
            agregado_tipo='pedido', agregado_id='0', producto_ref=None,
            payload={'usuario_id': USUARIO_PRUEBA, 'oferta_ids': [1]},
        )
        outbox.project_event(evento)
        outbox.project_event(evento)  # repetirlo no falla ni toca lo demás
        assert [i['oferta_id'] for i in rcs.obtener_carrito(r, USUARIO_PRUEBA)] == [2]
    finally:
        r.delete(f'carrito:{USUARIO_PRUEBA}')


# ── Aislamiento, backoff y fallidos ───────────────────────────────────────────

def test_cada_consumidor_solo_toma_eventos_de_su_destino(eventos_creados, ref_dell):
    with SessionLocal() as db:
        filas = _encolar(
            db, eventos_creados, tipo_evento='inventario.actualizado', agregado_tipo='prueba',
            agregado_id='consumidor-destino', producto_ref=ref_dell, payload={},
        )
        db.commit()
        nuestros = {f.id for f in filas}
        por_destino = {f.destino: f.id for f in filas}
    # Lo que reclama cada consumidor siempre es de su destino (si un backend de
    # desarrollo está corriendo puede adelantarse y reclamar primero: por eso
    # se acepta None, pero nunca un evento de otro destino).
    reclamado = outbox._claim_one('cassandra')
    assert reclamado not in nuestros
    reclamado = outbox._claim_one('busqueda')
    assert reclamado in (None, por_destino['busqueda'])
    with SessionLocal() as db:
        for evento_id in filter(None, [reclamado]):
            evento = db.get(OutboxEvento, evento_id)
            assert evento.destino == 'busqueda' and evento.estado == 'procesando'
            evento.estado, evento.intentos = 'pendiente', 0  # se devuelve a la cola
        db.commit()


def test_endpoints_del_laboratorio_solo_existen_con_la_bandera():
    from fastapi import FastAPI

    from app.api.v1 import consistency

    rutas = {r.path for r in consistency.router_fallas.routes}
    assert {'/admin/fallas', '/admin/fallas/pasarela', '/admin/checkout/recuperar'} <= rutas
    # El diagnóstico de solo lectura no forma parte del control de fallas.
    assert not {r.path for r in consistency.router.routes} & {'/admin/fallas', '/admin/checkout/recuperar'}
    sin_bandera = FastAPI()
    sin_bandera.include_router(consistency.router, prefix='/api/v1')
    assert not [r for r in sin_bandera.routes if 'fallas' in getattr(r, 'path', '')]

def test_falla_de_un_destino_no_bloquea_a_los_demas_y_usa_backoff(eventos_creados, ref_dell):
    with SessionLocal() as db:
        roto = _encolar(
            db, eventos_creados, tipo_evento='grafo.compra_registrada', agregado_tipo='pedido',
            agregado_id='999999999', producto_ref=None, payload={},
        )[0]
        sano = _encolar(
            db, eventos_creados, tipo_evento='inventario.actualizado', agregado_tipo='prueba',
            agregado_id='aislamiento', producto_ref=ref_dell, payload={}, destinos=('mongo',),
        )[0]
        db.commit()
        roto_id, sano_id = roto.id, sano.id

    estados = _procesar_hasta([roto_id, sano_id], {'procesado', 'error'})
    assert estados == {roto_id: 'error', sano_id: 'procesado'}
    with SessionLocal() as db:
        evento = db.get(OutboxEvento, roto_id)
        assert evento.intentos == 1
        assert 'inexistente' in evento.ultimo_error
        espera = evento.siguiente_intento_en - evento.procesado_en
        assert timedelta(seconds=1) < espera <= timedelta(seconds=outbox.backoff_segundos(1) + 1)

    # Antes de que venza su espera, el evento en error no se vuelve a tomar.
    outbox._pausas.clear()
    assert _procesar_hasta([roto_id], {'procesado'}, intentos=5)[roto_id] == 'error'
    with SessionLocal() as db:
        assert db.get(OutboxEvento, roto_id).intentos == 1


def test_evento_agotado_queda_fallido_y_se_puede_reintentar(eventos_creados):
    with SessionLocal() as db:
        evento = _encolar(
            db, eventos_creados, tipo_evento='grafo.compra_registrada', agregado_tipo='pedido',
            agregado_id='999999998', producto_ref=None, payload={},
        )[0]
        evento.intentos = outbox.MAX_ATTEMPTS - 1
        db.commit()
        evento_id = evento.id

    assert _procesar_hasta([evento_id], {'fallido'})[evento_id] == 'fallido'
    with SessionLocal() as db:
        fallido = db.get(OutboxEvento, evento_id)
        assert fallido.siguiente_intento_en is None
        resumen = {r['destino']: r for r in outbox.resumen_por_destino(db)}
        assert resumen['neo4j']['fallido'] >= 1
        assert outbox.reintentar(db, evento_id=evento_id) == 1
        reintentado = db.get(OutboxEvento, evento_id)
        db.refresh(reintentado)
        assert (reintentado.estado, reintentado.intentos) == ('pendiente', 0)
