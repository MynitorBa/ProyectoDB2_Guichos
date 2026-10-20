"""API de búsqueda: tolerancia, relevancia, facetas, autocompletado y respaldo.

Usa el índice real (solo lectura) y los endpoints HTTP. El cliente se crea sin
el contexto de arranque para no levantar los workers en segundo plano.
"""

import pytest
from elasticsearch import Elasticsearch
from fastapi.testclient import TestClient

from app.core.deps import get_es
from app.main import app

client = TestClient(app)


def buscar(**params):
    respuesta = client.get('/api/v1/search', params=params)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def skus(resultado):
    return [item['sku'] for item in resultado['items']]


# ── Tolerancia y relevancia ───────────────────────────────────────────────────

@pytest.mark.parametrize('consulta, esperado', [
    ('lapto', 'Laptop'),             # error ortográfico / incompleta
    ('macbok', 'MacBook Air M2'),    # error ortográfico
    ('samsng galaxy', 'Samsung Galaxy A54'),
    ('harry poter', 'Harry Potter'),
    ('laptpo', 'Laptop'),            # letras invertidas
])
def test_tolera_errores_ortograficos(consulta, esperado):
    resultado = buscar(q=consulta)
    assert resultado['motor'] == 'elasticsearch' and not resultado['degradado']
    assert esperado in resultado['items'][0]['nombre']


@pytest.mark.parametrize('consulta, esperado', [
    ('audifonos sony', 'TECH-AUD-001'),   # sin tilde
    ('cafe huehuetenango', 'ALI-CAF-001'),
    ('cien anos', 'LIBRO-FIC-001'),
    ('zapatillas nike', 'ROPA-CAL-001'),  # sinónimo de tenis, y por encima del balón Nike
    ('inspiron dell', 'TECH-LAP-001'),    # orden de palabras
    ('sams', 'TECH-CEL-001'),             # prefijo
    ('tala', 'HER-TAL-001'),
    ('tech-lap-001', 'TECH-LAP-001'),     # SKU sin importar mayúsculas
])
def test_tildes_sinonimos_prefijos_y_sku(consulta, esperado):
    assert skus(buscar(q=consulta))[0] == esperado


def test_sinonimo_devuelve_solo_la_familia_correcta():
    resultado = buscar(q='telefono')
    assert resultado['total'] >= 3
    # Las ofertas DEMO tienen otros SKU, pero pertenecen a la misma familia.
    assert all(item['categoria']['slug'] == 'celulares' for item in resultado['items'])


def test_resaltado_marca_lo_que_coincidio():
    item = buscar(q='macbok')['items'][0]
    assert item['resaltado']['nombre'] == '<mark>MacBook</mark> Air M2'


def test_resaltado_escapa_html_del_catalogo():
    """El frontend pinta `resaltado` como HTML: solo debe contener <mark>."""
    from uuid import uuid4

    from app.services import search_index_service as indice
    from app.services.search_service import ParametrosBusqueda, como_argumentos, construir_consulta

    es = get_es().options(request_timeout=15)
    nombre = f'productos_test_{uuid4().hex[:12]}'
    indice.crear_indice(es, nombre)
    try:
        es.index(index=nombre, id='x', refresh=True, document={
            'producto_id': 'x', 'nombre': '<img src=x onerror=alert(1)> Laptop maliciosa',
            'estado': 'activo', 'tiene_stock': True,
        })
        cuerpo = construir_consulta(ParametrosBusqueda(q='laptop'))
        respuesta = es.search(index=nombre, **como_argumentos(cuerpo))
        resaltado = respuesta['hits']['hits'][0]['highlight']['nombre'][0]
    finally:
        es.options(ignore_status=404).indices.delete(index=nombre)
    assert '<img' not in resaltado
    assert '&lt;img' in resaltado
    assert '<mark>Laptop</mark>' in resaltado


def test_quisiste_decir_solo_ante_errores_reales():
    assert buscar(q='macbok')['sugerencia'] == 'macbook'
    assert buscar(q='harry poter')['sugerencia'] == 'harry potter'
    assert buscar(q='licu')['sugerencia'] is None      # búsqueda incompleta, no error
    assert buscar(q='laptop')['sugerencia'] is None


def test_sin_texto_ordena_por_mas_vendidos_y_con_texto_por_relevancia():
    assert buscar()['orden'] == 'mas_vendidos'
    assert buscar(q='laptop')['orden'] == 'relevancia'


def test_orden_por_precio_coincide_con_el_precio_mostrado():
    precios = [item['precio'] for item in buscar(orden='precio_desc', page_size=30)['items']]
    assert precios == sorted(precios, reverse=True)


# ── Facetas ───────────────────────────────────────────────────────────────────

def test_facetas_de_precio_cuadran_con_el_total():
    resultado = buscar(q='laptop')
    facetas = resultado['facetas']
    assert sum(r['conteo'] for r in facetas['precio']['rangos']) == resultado['total']
    assert facetas['disponibilidad']['con_stock'] <= resultado['total']
    assert {'computadoras'} <= {c['valor'] for c in facetas['categorias']}


def test_facetas_disyuntivas_conservan_las_otras_opciones():
    sin_filtro = buscar(q='laptop')['facetas']['vendedores']
    elegido = sin_filtro[0]
    filtrado = buscar(q='laptop', vendedor=elegido['valor'])
    # El total coincide con lo que anunciaba la faceta...
    assert filtrado['total'] == elegido['conteo']
    # ...y los demás vendedores siguen visibles con su conteo original.
    assert [(v['valor'], v['conteo']) for v in filtrado['facetas']['vendedores']] == \
        [(v['valor'], v['conteo']) for v in sin_filtro]
    assert next(v for v in filtrado['facetas']['vendedores'] if v['valor'] == elegido['valor'])['seleccionado']


def test_filtro_por_atributo_dinamico():
    base = buscar(categoria='camisas')
    tallas = next(a for a in base['facetas']['atributos'] if a['nombre'] == 'talla')
    talla = tallas['valores'][0]
    respuesta = client.get('/api/v1/search', params={'categoria': 'camisas', 'attr.talla': talla['valor']})
    filtrado = respuesta.json()
    assert filtrado['total'] == talla['conteo']
    faceta = next(a for a in filtrado['facetas']['atributos'] if a['nombre'] == 'talla')
    assert faceta['etiqueta'] == 'Talla'
    assert next(v for v in faceta['valores'] if v['valor'] == talla['valor'])['seleccionado']
    assert len(faceta['valores']) == len(tallas['valores'])  # disyuntiva dentro del atributo


def test_resultados_traen_precio_autoritativo_de_mysql():
    item = buscar(q='TECH-LAP-001')['items'][0]
    assert item['oferta_id'] is not None
    assert item['vendedor_nombre']
    assert 'dual_read' not in item


# ── Búsqueda dentro de una tienda ─────────────────────────────────────────────

def _vendedor_con_laptops():
    from app.core.db_mysql import SessionLocal
    from app.models.oferta import Oferta
    from app.models.vendedor import Vendedor

    with SessionLocal() as db:
        ref = get_mongo_ref('TECH-LAP-001')
        oferta = db.query(Oferta).filter_by(producto_ref=ref, estado='activa').first()
        return db.get(Vendedor, oferta.vendedor_id)


def get_mongo_ref(sku):
    from app.core.db_mongo import get_mongo_db
    return str(get_mongo_db().productos.find_one({'sku': sku}, {'_id': 1})['_id'])


def test_busqueda_en_tienda_solo_devuelve_ofertas_del_vendedor():
    vendedor = _vendedor_con_laptops()
    global_ = buscar(q='lapto')
    tienda = buscar(q='lapto', vendedor_id=vendedor.id)
    assert 0 < tienda['total'] <= global_['total']
    assert all(item['vendedor_id'] == vendedor.id for item in tienda['items'])
    # Los conteos de las facetas también respetan el alcance de la tienda.
    assert {v['valor'] for v in tienda['facetas']['vendedores']} >= {vendedor.nombre_comercial}
    assert sum(r['conteo'] for r in tienda['facetas']['precio']['rangos']) == tienda['total']


def test_busqueda_en_tienda_sin_coincidencias_no_sugiere_productos_ajenos():
    from app.core.db_mysql import SessionLocal
    from app.models.oferta import Oferta

    ref_macbook = get_mongo_ref('TECH-LAP-003')
    with SessionLocal() as db:
        con_macbook = {o.vendedor_id for o in db.query(Oferta).filter_by(producto_ref=ref_macbook)}
        from app.models.vendedor import Vendedor
        sin_macbook = next(v for v in db.query(Vendedor).all() if v.id not in con_macbook)
    resultado = buscar(q='macbok', vendedor_id=sin_macbook.id)
    assert resultado['total'] == 0
    assert resultado['sugerencia'] is None


def test_busqueda_en_tienda_degradada_conserva_el_alcance(elasticsearch_caido):
    vendedor = _vendedor_con_laptops()
    resultado = buscar(q='Laptop', vendedor_id=vendedor.id)
    assert resultado['degradado'] is True
    assert resultado['items']
    assert all(item['vendedor_id'] == vendedor.id for item in resultado['items'])


# ── Autocompletado ────────────────────────────────────────────────────────────

def test_autocompletado_por_prefijo_palabra_intermedia_y_errores():
    def nombres(q):
        respuesta = client.get('/api/v1/search/suggest', params={'q': q})
        assert respuesta.status_code == 200
        return [p['nombre'] for p in respuesta.json()['productos']]

    assert 'Samsung Galaxy A54' in nombres('sams')
    assert 'Samsung Galaxy A54' in nombres('galax')     # palabra que no es la primera
    assert 'Licuadora Oster 600W' in nombres('licuadroa')  # error al escribir
    categorias = client.get('/api/v1/search/suggest', params={'q': 'compu'}).json()['categorias']
    assert {'slug': 'computadoras', 'nombre': 'Computadoras'} in categorias
    assert client.get('/api/v1/search/suggest', params={'q': 's'}).status_code == 422


# ── Respaldo cuando Elasticsearch no responde ─────────────────────────────────

@pytest.fixture
def elasticsearch_caido():
    caido = Elasticsearch('http://127.0.0.1:1', request_timeout=0.5, max_retries=0)
    app.dependency_overrides[get_es] = lambda: caido
    yield
    app.dependency_overrides.pop(get_es, None)


def test_busqueda_degradada_a_mongodb(elasticsearch_caido):
    resultado = buscar(q='Laptop')
    assert resultado['degradado'] is True
    assert resultado['motor'] == 'mongodb'
    assert resultado['total'] >= 1
    assert all('laptop' in item['nombre'].lower() for item in resultado['items'])
    assert resultado['facetas']['categorias']


def test_autocompletado_degradado_a_mongodb(elasticsearch_caido):
    respuesta = client.get('/api/v1/search/suggest', params={'q': 'Laptop'}).json()
    assert respuesta['degradado'] is True
    assert respuesta['productos']
