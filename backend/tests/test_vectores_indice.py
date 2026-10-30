"""Vectores en el índice de búsqueda (Entrega 4, mapping v2)."""

import pytest
from elasticsearch import Elasticsearch

from app.core import salud
from app.core.config import settings
from app.core.db_elastic import get_es
from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import SessionLocal
from app.services import embeddings_client as emb
from app.services import search_index_service as indice


@pytest.fixture
def es() -> Elasticsearch:
    return get_es()


@pytest.fixture
def producto(es) -> str:
    return next(r for r in indice.ids_indexados(es))


def _indexar(es, ref) -> dict:
    with SessionLocal() as db:
        return indice.indexar_productos(es, db, get_mongo_db(), [ref], refrescar=True)


def _fuente(es, ref) -> dict:
    return es.get(index=settings.ES_INDEX_ALIAS, id=ref)['_source']


def test_el_mapping_v2_declara_el_vector_con_las_dimensiones_del_modelo():
    vector = indice.cargar_definicion()['mappings']['properties']['vector']
    assert indice.VERSION_MAPPING == 2
    assert vector['type'] == 'dense_vector' and vector['index'] is True
    assert vector['similarity'] == 'cosine'
    assert vector['index_options']['type'] == 'int8_hnsw'
    assert vector['dims'] == emb.estado()['dimensiones']


def test_el_indice_vigente_usa_el_mapping_con_vector(es):
    assert indice.indice_actual(es).startswith('productos_v2_')
    assert indice.indice_tiene_vector(es)


def test_indexar_calcula_el_vector_y_luego_lo_reutiliza(es, producto):
    _indexar(es, producto)
    fuente = _fuente(es, producto)
    assert len(fuente['vector']) == indice.dimensiones_vector()
    assert fuente['vector_modelo'] == settings.EMBEDDINGS_MODEL
    # Sin cambios en el texto del producto no se vuelve a llamar al modelo.
    assert _indexar(es, producto)['vectores'] == {'reutilizados': 1, 'calculados': 0, 'sin_vector': 0}


def test_sin_servicio_se_indexa_sin_vector_y_la_reconciliacion_lo_completa(es, producto):
    salud.registrar_falla('embeddings', 'caído', confirmada=True)
    try:
        # Un texto distinto obliga a recalcular: el vector anterior ya no sirve.
        documentos = {producto: {'nombre': 'Texto cambiado sin servicio'}}
        assert indice.adjuntar_vectores(es, documentos)['sin_vector'] == 1
        assert 'vector' not in documentos[producto]
    finally:
        salud.reiniciar()
    es.update(index=settings.ES_INDEX_ALIAS, id=producto, script={'source': "ctx._source.remove('vector')"},
              refresh=True)
    assert producto in indice.ids_sin_vector(es)
    with SessionLocal() as db:
        indice.reconciliar_desfasados(es, db, get_mongo_db())
    # La reconciliación no refresca: sin esto, el kNN de otras pruebas aún no vería el vector.
    es.indices.refresh(index=settings.ES_INDEX_ALIAS)
    assert 'vector' in _fuente(es, producto)
    assert producto not in indice.ids_sin_vector(es)


def test_un_indice_sin_campo_vector_sigue_recibiendo_documentos(es):
    nombre = 'productos_prueba_sin_vector'
    definicion = indice.cargar_definicion(1)
    es.indices.create(index=nombre, **definicion)
    try:
        documentos = {'abc': {'nombre': 'Producto de prueba'}}
        assert indice.adjuntar_vectores(es, documentos, indice=nombre)['calculados'] == 0
        assert 'vector' not in documentos['abc']
    finally:
        es.indices.delete(index=nombre)


def test_el_texto_del_vector_combina_los_campos_del_documento():
    texto = indice.texto_vector({
        'nombre': 'Licuadora Oster', 'categorias': [{'slug': 'hogar', 'nombre': 'Hogar'}],
        'descripcion': 'Diez velocidades.', 'texto_atributos': 'Negro 600W',
    })
    assert texto == 'Licuadora Oster. Categoría: Hogar. Diez velocidades. Negro 600W'


def test_busqueda_knn_encuentra_por_significado(es):
    vector = emb.generar(['algo para escuchar música sin cables'])[0]
    respuesta = es.search(index=settings.ES_INDEX_ALIAS, size=3, source=['nombre'],
                          knn={'field': 'vector', 'query_vector': vector, 'k': 3, 'num_candidates': 100})
    nombres = ' '.join(h['_source']['nombre'].lower() for h in respuesta['hits']['hits'])
    assert any(palabra in nombres for palabra in ('audífonos', 'airpods', 'bocina'))


def test_se_purgan_las_versiones_borradas_que_estorban_al_knn(es, producto):
    # Reindexar deja la versión anterior como borrada dentro del grafo HNSW.
    _indexar(es, producto)
    _indexar(es, producto)
    nombre = indice.indice_actual(es)

    def borrados():
        return es.indices.stats(index=nombre, metric='docs')['indices'][nombre]['primaries']['docs']['deleted']

    antes = borrados()
    assert antes > 0
    assert indice.depurar_borrados(es, maximo=0) == antes
    # Elasticsearch retiene unos segundos los borrados recientes (soft deletes para
    # recuperar réplicas): la fusión inmediata puede no quitarlos todos, nunca suma.
    assert borrados() <= antes
    # Por debajo del máximo no se hace nada.
    assert indice.depurar_borrados(es, maximo=1.0) == 0
