"""Control de acceso de Redis (Entrega final): cada usuario solo puede lo que su servicio necesita.

Reglas en database/redis/acl.conf; contraseñas en el .env de la raíz.
"""

from pathlib import Path

import pytest
import redis
from dotenv import dotenv_values

from app.core.config import settings

ENV_RAIZ = dotenv_values(Path(__file__).resolve().parents[2] / '.env')
LLAVE_PRUEBA = 'carrito:9900003'


def _cliente(usuario: str | None = None, clave: str | None = None) -> redis.Redis:
    return redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, username=usuario, password=clave,
                       decode_responses=True, socket_connect_timeout=2, socket_timeout=2)


@pytest.fixture(scope='module')
def api():
    return _cliente('tiendaya_api', ENV_RAIZ['REDIS_API_PASSWORD'])


@pytest.fixture(scope='module')
def lectura():
    return _cliente('tiendaya_lectura', ENV_RAIZ['REDIS_LECTURA_PASSWORD'])


@pytest.fixture(scope='module')
def admin():
    return _cliente('tiendaya_admin', ENV_RAIZ['REDIS_ADMIN_PASSWORD'])


@pytest.fixture
def llave(api):
    api.set(LLAVE_PRUEBA, 'x', ex=60)
    yield LLAVE_PRUEBA
    api.delete(LLAVE_PRUEBA)


def test_el_backend_se_conecta_con_su_usuario():
    assert settings.REDIS_USERNAME == 'tiendaya_api'


def test_sin_credenciales_no_se_puede_hacer_nada():
    with pytest.raises(redis.AuthenticationError):
        _cliente().ping()


def test_solo_con_contrasena_se_entra_como_lectura(llave):
    # Así se conecta Redis Commander: usuario «default», que solo lee.
    default = _cliente(None, ENV_RAIZ['REDIS_LECTURA_PASSWORD'])
    assert default.get(llave) == 'x'
    with pytest.raises(redis.exceptions.NoPermissionError):
        default.set(llave, 'y')
    with pytest.raises(redis.exceptions.NoPermissionError):
        default.flushall()


def test_contrasena_incorrecta():
    with pytest.raises(redis.AuthenticationError):
        _cliente('tiendaya_api', 'incorrecta').ping()


def test_el_backend_usa_sus_llaves(api, llave):
    assert api.get(llave) == 'x'
    assert api.hset('flash:9900003', 'disponibles', 1) == 1
    api.delete('flash:9900003')


@pytest.mark.parametrize('llave_ajena', ['otra:cosa', 'usuarios:1', 'sesion:admin'])
def test_el_backend_no_toca_llaves_fuera_de_sus_prefijos(api, llave_ajena):
    with pytest.raises(redis.exceptions.NoPermissionError):
        api.set(llave_ajena, 'x')
    with pytest.raises(redis.exceptions.NoPermissionError):
        api.get(llave_ajena)


@pytest.mark.parametrize('comando', [
    ('FLUSHALL',), ('FLUSHDB',), ('KEYS', '*'), ('CONFIG', 'GET', 'requirepass'), ('ACL', 'LIST'),
    ('SAVE',), ('SHUTDOWN',), ('INFO',), ('CLIENT', 'LIST'), ('MONITOR',),
])
def test_el_backend_no_puede_administrar(api, comando):
    with pytest.raises(redis.exceptions.NoPermissionError):
        api.execute_command(*comando)


def test_un_script_lua_tampoco_sale_de_los_prefijos(api):
    # Las ventas flash usan Lua; el ACL también se revisa dentro del script.
    with pytest.raises(redis.exceptions.ResponseError, match='ACL failure|No permissions'):
        api.eval("return redis.call('SET', 'otra:cosa', 1)", 0)


def test_lectura_lee_pero_no_escribe_ni_borra(lectura, llave):
    assert lectura.get(llave) == 'x'
    assert lectura.ttl(llave) > 0
    for operacion in (lambda: lectura.set(llave, 'y'), lambda: lectura.delete(llave),
                      lambda: lectura.expire(llave, 1), lambda: lectura.flushdb(), lambda: lectura.keys('*')):
        with pytest.raises(redis.exceptions.NoPermissionError):
            operacion()
    assert lectura.get(llave) == 'x'


def test_solo_el_admin_ve_y_cambia_los_permisos(admin):
    usuarios = admin.acl_users()
    assert {'default', 'tiendaya_api', 'tiendaya_lectura', 'tiendaya_admin'} <= set(usuarios)
    assert '+@read' in admin.acl_getuser('default')['categories']
