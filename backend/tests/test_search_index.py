"""Índice de búsqueda: mapping deliberado, construcción de documentos e indexado.

Las pruebas que escriben usan un índice temporal ``productos_test_<uuid>``
creado con la misma definición versionada; nunca tocan el índice real.
"""

import sys
from pathlib import Path
from uuid import uuid4

import pytest
from bson import ObjectId

from app.core.config import settings
from app.core.db_elastic import get_es
from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import SessionLocal
from app.services import search_index_service as indice
from app.services.offer_service import listar_ofertas_por_referencias

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from repair_text_encoding import reparar_texto  # noqa: E402


SKU_LAPTOP = 'TECH-LAP-001'


@pytest.fixture(scope='module')
def es():
    return get_es().options(request_timeout=15)


@pytest.fixture
def indice_temporal(es_indexador):
    nombre = f'productos_test_{uuid4().hex[:12]}'
    indice.crear_indice(es_indexador, nombre)
    yield nombre
    es_indexador.options(ignore_status=404).indices.delete(index=nombre)


@pytest.fixture(scope='module')
def ref_laptop():
    doc = get_mongo_db().productos.find_one({'sku': SKU_LAPTOP}, {'_id': 1})
    assert doc, 'El seed debe incluir la laptop Dell Inspiron 15'
    return str(doc['_id'])


def _tokens(es, index, analyzer, texto):
    return [t['token'] for t in es.indices.analyze(index=index, analyzer=analyzer, text=texto)['tokens']]


# ── Mapping deliberado ────────────────────────────────────────────────────────

def test_definicion_versionada_no_usa_el_mapping_por_defecto():
    definicion = indice.cargar_definicion()
    mappings = definicion['mappings']
    assert mappings['dynamic'] == 'strict'
    assert mappings['properties']['atributos']['type'] == 'nested'
    assert mappings['properties']['sugerencia']['type'] == 'completion'
    nombre = mappings['properties']['nombre']
    assert nombre['analyzer'] == 'es_texto'
    assert nombre['search_analyzer'] == 'es_texto_busqueda'
    assert {'autocompletar', 'sugeridor', 'orden'} <= set(nombre['fields'])


def test_analizadores_quitan_tildes_derivan_y_expanden_sinonimos(es_indexador, indice_temporal):
    assert _tokens(es_indexador, indice_temporal, 'es_texto', 'Audífonos') == \
        _tokens(es_indexador, indice_temporal, 'es_texto', 'audifonos')
    # Los sinónimos solo se aplican al consultar.
    busqueda = _tokens(es_indexador, indice_temporal, 'es_texto_busqueda', 'telefono')
    assert {'celular', 'movil'} <= set(busqueda)
    assert 'celular' not in _tokens(es_indexador, indice_temporal, 'es_texto', 'telefono')
    assert _tokens(es_indexador, indice_temporal, 'autocompletar', 'Sams')[:3] == ['sa', 'sam', 'sams']


def test_mapping_estricto_rechaza_campos_no_declarados(es, indice_temporal):
    with pytest.raises(Exception) as error:
        es.index(index=indice_temporal, id='x', document={'campo_inventado': 1})
    assert 'strict' in str(error.value).lower()


# ── Construcción del documento desde el estado actual ─────────────────────────

def test_documento_se_construye_con_el_estado_actual_de_mysql(ref_laptop):
    with SessionLocal() as db:
        documento = indice.construir_documentos(db, get_mongo_db(), [ref_laptop])[ref_laptop]
        ofertas = listar_ofertas_por_referencias(db, [ref_laptop])[ref_laptop]

    assert documento['producto_id'] == ref_laptop
    assert documento['sku'] == SKU_LAPTOP
    # El stock es la suma de todas las ofertas, no la proyección de MongoDB.
    assert documento['stock_total'] == sum(o['stock'] for o in ofertas)
    assert documento['precio_max'] == max(o['precio'] for o in ofertas)
    assert documento['tiene_stock'] == any(o['disponible'] for o in ofertas)
    assert documento['vendedores'] == sorted({o['vendedor_nombre'] for o in ofertas})
    assert {'slug': 'computadoras', 'nombre': 'Computadoras'} in documento['categorias']

    ram = next(a for a in documento['atributos'] if a['nombre'] == 'ram_gb')
    assert ram['valor_num'] == 8.0 and ram['facetable'] is True
    procesador = next(a for a in documento['atributos'] if a['nombre'] == 'procesador')
    assert procesador['facetable'] is False

    entradas = documento['sugerencia']['input']
    assert entradas[0] == 'Laptop Dell Inspiron 15'
    assert 'Dell Inspiron 15' in entradas
    assert '15' not in entradas


def test_producto_inexistente_o_inactivo_sale_del_indice():
    inexistente = str(ObjectId())
    with SessionLocal() as db:
        documentos = indice.construir_documentos(db, get_mongo_db(), [inexistente])
    assert documentos == {inexistente: None}


# ── Escritura idempotente y versionada ────────────────────────────────────────

def test_indexado_es_idempotente_y_rechaza_estado_mas_antiguo(es, indice_temporal, ref_laptop):
    with SessionLocal() as db:
        documentos = indice.construir_documentos(db, get_mongo_db(), [ref_laptop])

    primero = indice.escribir_documentos(es, documentos, indice=indice_temporal, version=2000, refrescar=True)
    assert primero['indexados'] == 1
    repetido = indice.escribir_documentos(es, documentos, indice=indice_temporal, version=2000, refrescar=True)
    assert repetido['indexados'] == 1  # external_gte acepta la misma versión

    viejo = {ref_laptop: {**documentos[ref_laptop], 'nombre': 'Estado obsoleto'}}
    resultado = indice.escribir_documentos(es, viejo, indice=indice_temporal, version=1000, refrescar=True)
    assert resultado['omitidos'] == 1
    assert es.get(index=indice_temporal, id=ref_laptop)['_source']['nombre'] == 'Laptop Dell Inspiron 15'

    eliminado = indice.escribir_documentos(es, {ref_laptop: None}, indice=indice_temporal, version=3000, refrescar=True)
    assert eliminado['eliminados'] == 1
    assert es.count(index=indice_temporal)['count'] == 0


def test_busqueda_difusa_y_autocompletado_sobre_documentos_reales(es, indice_temporal):
    with SessionLocal() as db:
        documentos = indice.construir_documentos(db, get_mongo_db())
    indice.escribir_documentos(es, documentos, indice=indice_temporal, refrescar=True)

    difusa = es.search(index=indice_temporal, query={
        'match': {'nombre': {'query': 'macbok', 'fuzziness': 'AUTO'}}
    })
    assert difusa['hits']['hits'][0]['_source']['sku'] == 'TECH-LAP-003'

    sugerencias = es.search(index=indice_temporal, suggest={
        'productos': {'prefix': 'galax', 'completion': {'field': 'sugerencia'}}
    })['suggest']['productos'][0]['options']
    assert any(op['_source']['sku'] == 'TECH-CEL-001' for op in sugerencias)


# ── Índice real y calidad de datos ────────────────────────────────────────────

def test_alias_real_contiene_todos_los_productos_activos(es):
    activos = get_mongo_db().productos.count_documents({'estado': 'activo'})
    assert indice.indice_actual(es) is not None
    assert es.count(index=settings.ES_INDEX_ALIAS)['count'] == activos


def test_reparacion_de_mojibake_es_reversible_e_idempotente():
    assert reparar_texto('Cien aÃ±os de soledad â€” GarcÃ\xada MÃ¡rquez') == \
        'Cien años de soledad — García Márquez'
    assert reparar_texto('Audífonos Sony') == 'Audífonos Sony'
    assert reparar_texto(reparar_texto('Clean Code â€” Robert C. Martin')) == 'Clean Code — Robert C. Martin'
    assert get_mongo_db().productos.count_documents({'nombre': {'$regex': 'Ã|â€'}}) == 0
