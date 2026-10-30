"""Control de acceso de MongoDB (Entrega final): un usuario por servicio, con mínimo privilegio.

Rol y usuarios en database/mongo/03_usuarios.js; contraseñas en el .env de la raíz.
Las negaciones peligrosas (drop sobre colecciones reales) no se intentan: se comprueba que el
usuario no tenga la acción, para que un error de configuración no pueda borrar datos.
"""

from pathlib import Path

import pytest
from bson import ObjectId
from dotenv import dotenv_values
from pymongo import MongoClient
from pymongo.errors import OperationFailure

from app.core.config import settings

ENV_RAIZ = dotenv_values(Path(__file__).resolve().parents[2] / '.env')
SERVIDOR = settings.MONGO_URI.split('@')[-1].split('/')[0]
BASE = settings.MONGO_DB
COLECCIONES_APP = {'productos', 'producto_variantes', 'producto_eventos', 'categoria_esquemas', 'tiendas_config'}


def _cliente(usuario: str | None = None, clave: str | None = None) -> MongoClient:
    credenciales = f'{usuario}:{clave}@' if usuario else ''
    return MongoClient(f'mongodb://{credenciales}{SERVIDOR}/{BASE}?authSource={BASE}', serverSelectionTimeoutMS=3000)


@pytest.fixture(scope='module')
def api():
    return _cliente('tiendaya_api', ENV_RAIZ['MONGO_API_PASSWORD'])[BASE]


@pytest.fixture(scope='module')
def lectura():
    return _cliente('tiendaya_lectura', ENV_RAIZ['MONGO_LECTURA_PASSWORD'])[BASE]


@pytest.fixture(scope='module')
def admin():
    return _cliente('tiendaya_admin', ENV_RAIZ['MONGO_ADMIN_PASSWORD'])


def _acciones(db) -> dict[str, set[str]]:
    """Colección → acciones que tiene el usuario conectado (según MongoDB)."""
    estado = db.command('connectionStatus', showPrivileges=True)['authInfo']['authenticatedUserPrivileges']
    acciones: dict[str, set[str]] = {}
    for privilegio in estado:
        recurso = privilegio['resource']
        clave = f"{recurso.get('db', '*')}.{recurso.get('collection', '*')}" if 'db' in recurso else 'cluster'
        acciones.setdefault(clave, set()).update(privilegio['actions'])
    return acciones


def test_el_backend_se_conecta_con_su_usuario():
    assert 'tiendaya_api:' in settings.MONGO_URI


def test_sin_credenciales_no_se_lee_nada():
    with pytest.raises(OperationFailure, match='requires authentication'):
        _cliente()[BASE].productos.find_one()


def test_contrasena_incorrecta():
    with pytest.raises(OperationFailure, match='Authentication failed'):
        _cliente('tiendaya_api', 'incorrecta')[BASE].productos.find_one()


def test_el_backend_lee_y_escribe_sus_colecciones(api):
    referencia = ObjectId()
    api.producto_eventos.insert_one({'_id': referencia, 'tipo': 'prueba_permisos'})
    try:
        assert api.producto_eventos.update_one({'_id': referencia}, {'$set': {'ok': True}}).modified_count == 1
        assert api.producto_eventos.find_one({'_id': referencia})['ok'] is True
    finally:
        assert api.producto_eventos.delete_one({'_id': referencia}).deleted_count == 1
    assert api.productos.count_documents({}) > 0
    assert 'idx_categorias_estado' in api.productos.index_information()


def test_el_backend_solo_tiene_las_acciones_de_su_rol(api):
    acciones = _acciones(api)
    assert {clave.split('.', 1)[1] for clave in acciones if clave.startswith(f'{BASE}.')} == COLECCIONES_APP
    for clave, permitidas in acciones.items():
        assert permitidas <= {'find', 'insert', 'update', 'remove', 'createIndex', 'listIndexes'}, clave
    # Nada sobre el servidor ni sobre otras bases.
    assert all(clave.startswith(f'{BASE}.') for clave in acciones)


@pytest.mark.parametrize('operacion', [
    lambda db: db.migraciones.find_one(),                         # colección fuera de su rol
    lambda db: db.coleccion_ajena_permisos.insert_one({'x': 1}),  # no puede crear colecciones
    lambda db: db.list_collection_names(),
    lambda db: db.client['admin'].system.users.find_one(),        # otra base
    lambda db: db.client['tiendaya_demo'].productos.find_one(),
    lambda db: db.client.drop_database('tiendaya_prueba_permisos'),
    lambda db: db.command('createUser', 'intruso', pwd='x', roles=['root']),
    lambda db: db.command('grantRolesToUser', 'tiendaya_api', roles=['dbOwner']),
])
def test_el_backend_no_sale_de_su_alcance(api, operacion):
    with pytest.raises(OperationFailure, match='not authorized'):
        operacion(api)


def test_lectura_lee_pero_no_escribe(lectura):
    assert lectura.productos.count_documents({}) > 0
    for operacion in (lambda: lectura.productos.insert_one({'x': 1}),
                      lambda: lectura.productos.update_one({}, {'$set': {'x': 1}}),
                      lambda: lectura.productos.delete_one({'_id': ObjectId()}),
                      lambda: lectura.productos.create_index('x')):
        with pytest.raises(OperationFailure, match='not authorized'):
            operacion()


def test_admin_es_dueno_solo_de_la_base_de_la_tienda(admin):
    db = admin[BASE]
    db.create_collection('coleccion_prueba_admin')
    db.drop_collection('coleccion_prueba_admin')
    with pytest.raises(OperationFailure, match='not authorized'):
        admin['admin'].system.users.find_one()
    with pytest.raises(OperationFailure, match='not authorized'):
        admin['tiendaya_demo'].productos.find_one()
