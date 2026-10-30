"""Búsqueda híbrida: texto + vectores (Entrega 4)."""

import hashlib

import pytest
from fastapi.testclient import TestClient

from app.core import salud
from app.core.config import settings
from app.core.db_redis import get_redis
from app.main import app
from app.services import search_service

client = TestClient(app)

PARA_ESCUCHAR = 'algo para escuchar música sin cables'


def buscar(**params):
    respuesta = client.get('/api/v1/search', params=params)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def tipos(resultado):
    return [item['coincidencia'] for item in resultado['items']]


def test_las_coincidencias_de_texto_van_antes_que_las_relacionadas():
    resultado = buscar(q='samsung')
    assert resultado['semantica'] is True and resultado['sin_coincidencias'] is False
    assert resultado['items'][0]['nombre'] == 'Samsung Galaxy A54'
    # Primero todo lo que contiene el texto y después, lo parecido por significado.
    assert tipos(resultado) == sorted(tipos(resultado), key=lambda t: t != 'texto')
    relacionados = [i['nombre'] for i in resultado['items'] if i['coincidencia'] == 'semantica']
    assert relacionados and all('samsung' not in n.lower() for n in relacionados)
    assert sum(r['conteo'] for r in resultado['facetas']['precio']['rangos']) == resultado['total']


def test_sin_palabras_en_comun_encuentra_por_significado():
    resultado = buscar(q=PARA_ESCUCHAR)
    assert resultado['sin_coincidencias'] is True
    assert resultado['alternativa'] == 'semanticos' and resultado['consulta'] == PARA_ESCUCHAR
    nombres = ' '.join(i['nombre'].lower() for i in resultado['items'])
    assert 'airpods' in nombres or 'audífonos' in nombres
    assert set(tipos(resultado)) == {'semantica'}


def test_texto_sin_sentido_no_inventa_relacionados():
    resultado = buscar(q='hefkjdshafh')
    assert resultado['alternativa'] == 'populares'


def test_ordenando_por_precio_solo_cuentan_las_coincidencias_de_texto():
    resultado = buscar(q='samsung', orden='precio_asc')
    assert resultado['semantica'] is False
    assert all('samsung' in i['nombre'].lower() for i in resultado['items'])
    # Sin coincidencias, el respaldo por significado respeta el orden elegido.
    alternativa = buscar(q=PARA_ESCUCHAR, orden='precio_asc')
    assert alternativa['alternativa'] == 'semanticos'
    precios = [i['precio'] for i in alternativa['items']]
    assert precios == sorted(precios)


def test_el_vector_de_la_consulta_se_guarda_en_redis():
    texto = 'audífonos para correr'
    clave = 'vector_consulta:' + hashlib.sha1(
        f'{settings.EMBEDDINGS_MODEL}\n{texto}'.encode('utf-8')).hexdigest()
    get_redis().delete(clave)
    buscar(q='Audífonos  para CORRER')
    assert get_redis().ttl(clave) > 0


def test_sin_servicio_de_embeddings_la_busqueda_es_solo_de_texto():
    salud.registrar_falla('embeddings', 'caído', confirmada=True)
    try:
        resultado = buscar(q='zapatos de fútbol para niño')
    finally:
        salud.reiniciar()
    assert resultado['semantica'] is False and not resultado['degradado']
    assert resultado['items'] and all('coincidencia' not in i for i in resultado['items'])


@pytest.mark.parametrize('consulta', ['portátil liviana', 'portatil liviana'])
def test_dentro_de_una_tienda_los_relacionados_son_de_esa_tienda(consulta):
    from tests.test_search_api import _vendedor_con_laptops

    vendedor = _vendedor_con_laptops()
    resultado = buscar(q=consulta, vendedor_id=vendedor.id)
    assert resultado['items']
    assert all(item['vendedor_id'] == vendedor.id for item in resultado['items'])


def test_umbral_y_base_garantizan_el_orden():
    # Una relacionada suma como mucho PESO_SEMANTICO; toda coincidencia de texto, BASE_TEXTO.
    assert search_service.PESO_SEMANTICO < search_service.BASE_TEXTO
    assert 0 < search_service.UMBRAL_SEMANTICO < 1


def test_una_coincidencia_parcial_no_queda_antes_que_lo_relacionado():
    # «novela» se parece a «nivel» (nivel láser), pero no coincide con todas las palabras.
    resultado = buscar(q='novela de fantasía')
    assert resultado['items'][0]['categoria']['slug'] == 'libros'
    assert resultado['items'][0]['coincidencia'] == 'semantica'
