"""Plan B de Neo4j: caché de recomendaciones en MySQL y fraude por grafo pendiente."""

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable
from sqlalchemy import text

from app.core import salud
from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import SessionLocal
from app.core.db_neo4j import get_driver
from app.main import app
from app.models.fraud_analysis_run import FraudAnalysisRun
from app.services import recommendation_service as reco
from app.services.fraud_analysis_service import grafo_no_disponible, run_fraud_analysis_once

client = TestClient(app)


@pytest.fixture(scope='module', autouse=True)
def cache_al_dia():
    with SessionLocal() as db, get_driver().session() as neo4j:
        reco.recalcular_cache(neo4j, db)


def _neo4j_caido():
    salud.registrar_falla('neo4j', 'caído', confirmada=True)


def _producto_con_recomendaciones() -> str:
    mongo = get_mongo_db()
    with SessionLocal() as db:
        refs = db.execute(text(
            'SELECT DISTINCT producto_ref FROM recomendaciones_cache ORDER BY producto_ref'
        )).scalars().all()
        for ref in refs:
            items, origen = reco.recomendar_con_origen(db, mongo, producto_ref=ref)
            if items and origen == 'grafo':
                return ref
    pytest.skip('Ningún producto tiene recomendaciones de su misma categoría en estos datos.')


def test_la_cache_guarda_el_recorrido_y_recalcularla_no_cambia_nada():
    with SessionLocal() as db, get_driver().session() as neo4j:
        antes = db.execute(text('SELECT producto_ref, recomendado_ref, compradores_comunes '
                                'FROM recomendaciones_cache ORDER BY 1, 2')).all()
        reco.recalcular_cache(neo4j, db)
        despues = db.execute(text('SELECT producto_ref, recomendado_ref, compradores_comunes '
                                  'FROM recomendaciones_cache ORDER BY 1, 2')).all()
    assert antes and antes == despues
    assert all(fila.producto_ref != fila.recomendado_ref for fila in antes)


def test_sin_neo4j_las_recomendaciones_salen_de_la_cache_con_el_mismo_resultado():
    ref, mongo = _producto_con_recomendaciones(), get_mongo_db()
    with SessionLocal() as db:
        del_grafo, _ = reco.recomendar_con_origen(db, mongo, producto_ref=ref)
        _neo4j_caido()
        de_cache, origen = reco.recomendar_con_origen(db, mongo, producto_ref=ref)
    assert origen == 'cache'
    assert [i['_id'] for i in de_cache] == [i['_id'] for i in del_grafo]


def test_sin_cache_para_el_producto_se_muestran_los_mas_vendidos_de_su_categoria():
    ref, mongo = _producto_con_recomendaciones(), get_mongo_db()
    with SessionLocal() as db:
        guardadas = db.execute(text('SELECT * FROM recomendaciones_cache WHERE producto_ref = :r'),
                               {'r': ref}).mappings().all()
        db.execute(text('DELETE FROM recomendaciones_cache WHERE producto_ref = :r'), {'r': ref})
        db.commit()
        try:
            _neo4j_caido()
            items, origen = reco.recomendar_con_origen(db, mongo, producto_ref=ref)
        finally:
            db.execute(text("""
                INSERT INTO recomendaciones_cache VALUES
                (:producto_ref, :recomendado_ref, :compradores_comunes, :calculado_en)
            """), [dict(f) for f in guardadas])
            db.commit()
    base = mongo.productos.find_one({'_id': ObjectId(ref)})
    assert origen == 'mas_vendidos'
    assert items and all(reco.categoria_principal(i) == reco.categoria_principal(base) for i in items)
    assert all('unidades_vendidas' in i for i in items)


def test_la_cache_excluye_lo_que_el_usuario_ya_compro():
    with SessionLocal() as db:
        fila = db.execute(text("""
            SELECT c.producto_ref, c.recomendado_ref, p.usuario_id
            FROM recomendaciones_cache c
            JOIN pedido_lineas l ON l.producto_ref = c.recomendado_ref
            JOIN pedidos p ON p.id = l.pedido_id AND p.estado = 'entregado'
            LIMIT 1
        """)).first()
        if not fila:
            pytest.skip('Sin compras que excluir en estos datos.')
        candidatos = reco._desde_cache(db, fila.producto_ref, [fila.recomendado_ref], fila.usuario_id)
    assert candidatos == []


def test_endpoint_informa_el_origen():
    ref = _producto_con_recomendaciones()
    assert client.get(f'/api/v1/products/{ref}/recommendations').json()['origen'] == 'grafo'
    _neo4j_caido()
    datos = client.get(f'/api/v1/products/{ref}/recommendations').json()
    assert datos['origen'] == 'cache' and datos['items']


# ── Fraude ────────────────────────────────────────────────────────────────────

def _admin():
    token = client.post('/api/v1/auth/login', json={
        'email': 'admin@tiendaya.gt', 'password': 'password123',
    }).json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def test_resumen_de_fraude_sin_neo4j_marca_f01_f03_pendientes():
    encabezados = _admin()
    _neo4j_caido()
    respuesta = client.get('/api/v1/reviews/admin/fraude/resumen', headers=encabezados)
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos['grafo_disponible'] is False
    assert datos['bombardeo']['pendiente'] is True and datos['bombardeo']['count'] is None
    assert 'count' in datos['sin_compra_verificada']  # F04 sale de MySQL


def test_resumen_de_fraude_con_neo4j():
    datos = client.get('/api/v1/reviews/admin/fraude/resumen', headers=_admin()).json()
    assert datos['grafo_disponible'] is True
    assert isinstance(datos['bombardeo']['count'], int)


def test_analisis_sin_neo4j_queda_pendiente_y_se_reconoce():
    class DriverCaido:
        def session(self):
            raise ServiceUnavailable('Neo4j detenido')

    with pytest.raises(ServiceUnavailable) as error:
        run_fraud_analysis_once('manual', driver_override=DriverCaido())
    assert grafo_no_disponible(error.value)
    with SessionLocal() as db:
        run = db.query(FraudAnalysisRun).order_by(FraudAnalysisRun.id.desc()).first()
        try:
            assert run.estado == 'fallida'
            assert 'análisis pendiente' in run.error
        finally:
            db.delete(run)
            db.commit()
