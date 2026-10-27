"""Las recomendaciones de un producto solo incluyen productos de su misma categoría."""

import pytest

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import SessionLocal
from app.services.recommendation_service import (
    categoria_principal, recomendar, referencias_relacionadas, refs_misma_categoria,
)


class _Result:
    def data(self):
        return []


class _Session:
    def run(self, query, **params):
        self.query = query
        self.params = params
        return _Result()


def test_la_consulta_del_grafo_se_limita_a_los_productos_permitidos():
    session = _Session()
    referencias_relacionadas(session, 'a' * 24, limite=4, permitidos=['b' * 24])
    assert 'otro.ref IN $permitidos' in session.query
    assert session.params['permitidos'] == ['b' * 24]


def test_categoria_principal_usa_categoria_y_si_falta_la_primera_de_la_lista():
    assert categoria_principal({'categoria': {'slug': 'audio'}, 'categorias': [{'slug': 'x'}]}) == 'audio'
    assert categoria_principal({'categorias': [{'slug': 'libros'}, {'slug': 'x'}]}) == 'libros'
    assert categoria_principal({}) is None


def test_refs_misma_categoria_excluye_el_producto_y_otras_categorias():
    mongo = get_mongo_db()
    base = mongo.productos.find_one({'estado': 'activo', 'categoria.slug': {'$exists': True}})
    slug = categoria_principal(base)

    refs = refs_misma_categoria(mongo, str(base['_id']))

    assert str(base['_id']) not in refs
    for ref in refs:
        from bson import ObjectId
        assert categoria_principal(mongo.productos.find_one({'_id': ObjectId(ref)})) == slug


def test_producto_inexistente_no_recibe_recomendaciones():
    assert refs_misma_categoria(get_mongo_db(), 'no-es-un-id') == []


def test_las_recomendaciones_reales_son_de_la_misma_categoria():
    mongo = get_mongo_db()
    with SessionLocal() as mysql:
        for base in mongo.productos.find({'estado': 'activo'}, {'categoria': 1, 'categorias': 1}):
            items = recomendar(mysql, mongo, producto_ref=str(base['_id']), limite=8)
            if items:
                slug = categoria_principal(base)
                assert all(categoria_principal(item) == slug for item in items)
                return
    pytest.skip('Ningún producto tiene recomendaciones en estos datos.')
