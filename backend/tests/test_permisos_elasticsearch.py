"""Control de acceso de Elasticsearch (Entrega final): cada usuario con el rol de su servicio.

Roles y usuarios en database/elasticsearch/seguridad.json; contraseñas en el .env de la raíz.
Lo destructivo sobre el índice real (borrarlo) no se intenta: se pregunta a Elasticsearch con
``has_privileges`` si el usuario podría hacerlo.
"""

from pathlib import Path

import pytest
from dotenv import dotenv_values
from elasticsearch import AuthenticationException, AuthorizationException, Elasticsearch

from app.core.config import settings
from app.core.db_elastic import get_es

ENV_RAIZ = dotenv_values(Path(__file__).resolve().parents[2] / '.env')
ALIAS = settings.ES_INDEX_ALIAS
DOC_PRUEBA = 'prueba-permisos-es'


def _cliente(usuario: str | None = None, clave: str | None = None) -> Elasticsearch:
    return Elasticsearch(settings.ES_URL, basic_auth=(usuario, clave) if usuario else None, request_timeout=10)


@pytest.fixture(scope='module')
def api():
    return get_es()


@pytest.fixture(scope='module')
def lectura():
    return _cliente('tiendaya_lectura', ENV_RAIZ['ES_LECTURA_PASSWORD'])


def _puede(es, *privilegios, indice=ALIAS) -> dict[str, bool]:
    respuesta = es.security.has_privileges(index=[{'names': [indice], 'privileges': list(privilegios)}])
    return respuesta['index'][indice]


def test_el_backend_se_conecta_con_su_usuario(api):
    assert settings.ES_USERNAME == 'tiendaya_api'
    assert api.security.authenticate()['roles'] == ['tiendaya_busqueda']


def test_sin_credenciales_no_se_consulta_nada():
    with pytest.raises(AuthenticationException):
        _cliente().count(index=ALIAS)


def test_contrasena_incorrecta():
    with pytest.raises(AuthenticationException):
        _cliente('tiendaya_api', 'incorrecta').count(index=ALIAS)


def test_el_backend_busca_y_mantiene_documentos(api):
    assert api.count(index=ALIAS)['count'] > 0
    api.index(index=ALIAS, id=DOC_PRUEBA, document={'nombre': 'Prueba de permisos', 'estado': 'inactivo'}, refresh=True)
    try:
        api.update(index=ALIAS, id=DOC_PRUEBA, doc={'nombre': 'Prueba de permisos editada'}, refresh=True)
        assert api.get(index=ALIAS, id=DOC_PRUEBA)['_source']['nombre'] == 'Prueba de permisos editada'
    finally:
        api.delete(index=ALIAS, id=DOC_PRUEBA, refresh=True)
    assert api.indices.get_mapping(index=ALIAS)
    assert api.indices.stats(index=ALIAS, metric='docs')


def test_el_backend_no_puede_borrar_ni_reconfigurar_el_indice(api):
    assert _puede(api, 'read', 'write', 'maintenance') == {'read': True, 'write': True, 'maintenance': True}
    assert _puede(api, 'delete_index', 'create_index', 'manage', 'all') == {
        'delete_index': False, 'create_index': False, 'manage': False, 'all': False,
    }


@pytest.mark.parametrize('operacion', [
    lambda es: es.indices.create(index='productos_intruso'),
    lambda es: es.indices.put_alias(index=ALIAS, name='productos_alias_intruso'),
    lambda es: es.indices.put_settings(index=ALIAS, settings={'number_of_replicas': 1}),
    lambda es: es.search(index='.security-7'),
    lambda es: es.cluster.put_settings(persistent={'cluster.routing.allocation.enable': 'none'}),
    lambda es: es.security.put_user(username='intruso', password='intruso123', roles=['superuser']),
    lambda es: es.security.get_user(),
])
def test_el_backend_no_sale_de_su_alcance(api, es_indexador, operacion):
    try:
        with pytest.raises(AuthorizationException):
            operacion(api)
    finally:
        # Si alguna vez se permitiera, no dejar rastros.
        es_indexador.options(ignore_status=404).indices.delete(index='productos_intruso')


def test_lectura_busca_pero_no_escribe(lectura):
    assert lectura.count(index=ALIAS)['count'] > 0
    with pytest.raises(AuthorizationException):
        lectura.index(index=ALIAS, id=DOC_PRUEBA, document={'nombre': 'x'})
    with pytest.raises(AuthorizationException):
        lectura.delete(index=ALIAS, id='cualquiera')
    assert _puede(lectura, 'read', 'write') == {'read': True, 'write': False}


def test_el_indexador_administra_solo_los_indices_del_catalogo(es_indexador):
    es_indexador.indices.create(index='productos_test_permisos')
    es_indexador.indices.delete(index='productos_test_permisos')
    with pytest.raises(AuthorizationException):
        es_indexador.indices.create(index='otro_indice_permisos')
    with pytest.raises(AuthorizationException):
        es_indexador.security.get_user()
