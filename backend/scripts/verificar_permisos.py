"""Evidencia del control de acceso de Redis, MongoDB y Elasticsearch (Entrega final).

Con cada usuario de cada componente intenta operaciones permitidas y prohibidas contra el sistema
en marcha, compara con lo esperado y deja el resultado en docs/evidencia/permisos.md (y en la
consola). Nunca muestra contraseñas. Lo que borraría datos reales no se ejecuta: se pregunta al
motor si el usuario tiene ese privilegio.

Uso (desde backend/, con los contenedores arriba y scripts/configurar-acceso.ps1 ya ejecutado):
    venv/Scripts/python.exe scripts/verificar_permisos.py
Sale con código 1 si algún resultado no es el esperado.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import redis
from bson import ObjectId
from dotenv import dotenv_values
from elasticsearch import AuthenticationException, AuthorizationException, Elasticsearch
from pymongo import MongoClient
from pymongo.errors import OperationFailure

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'backend'))

from app.core.config import settings  # noqa: E402

ENV = dotenv_values(RAIZ / '.env')
SALIDA = RAIZ / 'docs' / 'evidencia' / 'permisos.md'
PERMITIDO, DENEGADO = 'permitido', 'denegado'


@dataclass
class Prueba:
    componente: str
    usuario: str
    intento: str
    esperado: str
    obtenido: str = ''
    detalle: str = ''

    @property
    def ok(self) -> bool:
        return self.esperado == self.obtenido


def ejecutar(prueba: Prueba, accion: Callable[[], object], errores: tuple[type[BaseException], ...]) -> Prueba:
    try:
        accion()
        prueba.obtenido = PERMITIDO
    except errores as exc:
        prueba.obtenido = DENEGADO
        prueba.detalle = str(exc).split('\n')[0][:110]
    return prueba


# ── Redis ─────────────────────────────────────────────────────────────────────

def pruebas_redis() -> list[Prueba]:
    def cliente(usuario, clave):
        return redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, username=usuario, password=clave,
                           decode_responses=True, socket_connect_timeout=3, socket_timeout=3)

    api = cliente('tiendaya_api', ENV.get('REDIS_API_PASSWORD'))
    lectura = cliente('tiendaya_lectura', ENV.get('REDIS_LECTURA_PASSWORD'))
    admin = cliente('tiendaya_admin', ENV.get('REDIS_ADMIN_PASSWORD'))
    llave = 'carrito:9900099'
    denegado = (redis.exceptions.AuthenticationError, redis.exceptions.NoPermissionError, redis.exceptions.ResponseError)
    casos = [
        ('(sin credenciales)', 'PING', DENEGADO, lambda: cliente(None, None).ping()),
        ('tiendaya_api', 'PING con contraseña incorrecta', DENEGADO, lambda: cliente('tiendaya_api', 'incorrecta').ping()),
        ('tiendaya_api', f'SET {llave} (su prefijo carrito:*)', PERMITIDO, lambda: api.set(llave, 'x', ex=60)),
        ('tiendaya_api', 'SET otra:cosa (fuera de sus prefijos)', DENEGADO, lambda: api.set('otra:cosa', 'x')),
        ('tiendaya_api', 'FLUSHALL', DENEGADO, lambda: api.execute_command('FLUSHALL')),
        ('tiendaya_api', 'KEYS *', DENEGADO, lambda: api.execute_command('KEYS', '*')),
        ('tiendaya_api', 'CONFIG GET requirepass', DENEGADO, lambda: api.execute_command('CONFIG', 'GET', 'requirepass')),
        ('tiendaya_api', 'ACL LIST', DENEGADO, lambda: api.execute_command('ACL', 'LIST')),
        ('tiendaya_api', 'Lua que escribe otra:cosa', DENEGADO, lambda: api.eval("return redis.call('SET','otra:cosa',1)", 0)),
        ('tiendaya_lectura', f'GET {llave}', PERMITIDO, lambda: lectura.get(llave)),
        ('tiendaya_lectura', f'SET {llave}', DENEGADO, lambda: lectura.set(llave, 'y')),
        ('tiendaya_lectura', f'DEL {llave}', DENEGADO, lambda: lectura.delete(llave)),
        ('default (solo contraseña)', f'GET {llave}', PERMITIDO, lambda: cliente(None, ENV.get('REDIS_LECTURA_PASSWORD')).get(llave)),
        ('default (solo contraseña)', 'FLUSHALL', DENEGADO, lambda: cliente(None, ENV.get('REDIS_LECTURA_PASSWORD')).flushall()),
        ('tiendaya_admin', 'ACL USERS', PERMITIDO, lambda: admin.acl_users()),
    ]
    resultado = [ejecutar(Prueba('Redis', u, i, e), a, denegado) for u, i, e, a in casos]
    api.delete(llave)
    return resultado


# ── MongoDB ───────────────────────────────────────────────────────────────────

def pruebas_mongo() -> list[Prueba]:
    servidor = settings.MONGO_URI.split('@')[-1].split('/')[0]
    base = settings.MONGO_DB

    def cliente(usuario, clave):
        credenciales = f'{usuario}:{clave}@' if usuario else ''
        return MongoClient(f'mongodb://{credenciales}{servidor}/{base}?authSource={base}', serverSelectionTimeoutMS=3000)[base]

    api = cliente('tiendaya_api', ENV.get('MONGO_API_PASSWORD'))
    lectura = cliente('tiendaya_lectura', ENV.get('MONGO_LECTURA_PASSWORD'))
    admin = cliente('tiendaya_admin', ENV.get('MONGO_ADMIN_PASSWORD'))
    marca = ObjectId()

    def acciones_api() -> None:
        estado = api.command('connectionStatus', showPrivileges=True)['authInfo']['authenticatedUserPrivileges']
        if any('dropCollection' in p['actions'] or 'dropDatabase' in p['actions'] for p in estado):
            raise OperationFailure('tiene dropCollection o dropDatabase')

    casos = [
        ('(sin credenciales)', 'find en productos', DENEGADO, lambda: cliente(None, None).productos.find_one()),
        ('tiendaya_api', 'find con contraseña incorrecta', DENEGADO, lambda: cliente('tiendaya_api', 'incorrecta').productos.find_one()),
        ('tiendaya_api', 'find en productos', PERMITIDO, lambda: api.productos.find_one()),
        ('tiendaya_api', 'insert y delete en producto_eventos', PERMITIDO,
         lambda: (api.producto_eventos.insert_one({'_id': marca, 'tipo': 'verificar_permisos'}),
                  api.producto_eventos.delete_one({'_id': marca}))),
        ('tiendaya_api', 'no tiene dropCollection ni dropDatabase (connectionStatus)', PERMITIDO, acciones_api),
        ('tiendaya_api', 'find en migraciones (fuera de su rol)', DENEGADO, lambda: api.migraciones.find_one()),
        ('tiendaya_api', 'insert en una colección nueva', DENEGADO, lambda: api.coleccion_ajena.insert_one({'x': 1})),
        ('tiendaya_api', 'find en admin.system.users', DENEGADO, lambda: api.client['admin'].system.users.find_one()),
        ('tiendaya_api', 'createUser intruso con rol root', DENEGADO,
         lambda: api.command('createUser', 'intruso', pwd='x', roles=['root'])),
        ('tiendaya_lectura', 'count en productos', PERMITIDO, lambda: lectura.productos.count_documents({})),
        ('tiendaya_lectura', 'insert en productos', DENEGADO, lambda: lectura.productos.insert_one({'x': 1})),
        ('tiendaya_admin', 'crear y borrar una colección de prueba en tiendaya', PERMITIDO,
         lambda: (admin.create_collection('verificar_permisos_tmp'), admin.drop_collection('verificar_permisos_tmp'))),
        ('tiendaya_admin', 'find en admin.system.users', DENEGADO, lambda: admin.client['admin'].system.users.find_one()),
    ]
    return [ejecutar(Prueba('MongoDB', u, i, e), a, (OperationFailure,)) for u, i, e, a in casos]


# ── Elasticsearch ─────────────────────────────────────────────────────────────

def pruebas_elasticsearch() -> list[Prueba]:
    def cliente(usuario, clave):
        return Elasticsearch(settings.ES_URL, basic_auth=(usuario, clave) if usuario else None, request_timeout=10)

    alias = settings.ES_INDEX_ALIAS
    api = cliente('tiendaya_api', ENV.get('ES_API_PASSWORD'))
    lectura = cliente('tiendaya_lectura', ENV.get('ES_LECTURA_PASSWORD'))
    indexador = cliente('tiendaya_indexador', ENV.get('ES_INDEXADOR_PASSWORD'))

    def sin_borrar_indice() -> None:
        privilegios = api.security.has_privileges(
            index=[{'names': [alias], 'privileges': ['delete_index', 'create_index', 'manage']}])['index'][alias]
        if any(privilegios.values()):
            raise AuthorizationException(message=f'tiene {privilegios}', meta=None, body=None)

    casos = [
        ('(sin credenciales)', f'count en {alias}', DENEGADO, lambda: cliente(None, None).count(index=alias)),
        ('tiendaya_api', 'count con contraseña incorrecta', DENEGADO, lambda: cliente('tiendaya_api', 'incorrecta').count(index=alias)),
        ('tiendaya_api', f'search en {alias}', PERMITIDO, lambda: api.search(index=alias, size=1)),
        ('tiendaya_api', 'no puede borrar, crear ni administrar el índice (has_privileges)', PERMITIDO, sin_borrar_indice),
        ('tiendaya_api', 'crear el índice productos_intruso', DENEGADO, lambda: api.indices.create(index='productos_intruso')),
        ('tiendaya_api', f'agregar un alias a {alias}', DENEGADO, lambda: api.indices.put_alias(index=alias, name='alias_intruso')),
        ('tiendaya_api', 'search en .security-7', DENEGADO, lambda: api.search(index='.security-7')),
        ('tiendaya_api', 'crear un usuario superuser', DENEGADO,
         lambda: api.security.put_user(username='intruso', password='intruso123', roles=['superuser'])),
        ('tiendaya_lectura', f'search en {alias}', PERMITIDO, lambda: lectura.search(index=alias, size=1)),
        ('tiendaya_lectura', f'index de un documento en {alias}', DENEGADO,
         lambda: lectura.index(index=alias, id='verificar-permisos', document={'nombre': 'x'})),
        ('tiendaya_indexador', 'crear y borrar productos_verificar_tmp', PERMITIDO,
         lambda: (indexador.indices.create(index='productos_verificar_tmp'), indexador.indices.delete(index='productos_verificar_tmp'))),
        ('tiendaya_indexador', 'crear otro_indice_verificar (fuera de productos*)', DENEGADO,
         lambda: indexador.indices.create(index='otro_indice_verificar')),
    ]
    resultado = [ejecutar(Prueba('Elasticsearch', u, i, e), a, (AuthenticationException, AuthorizationException))
                 for u, i, e, a in casos]
    for nombre in ('productos_intruso', 'otro_indice_verificar'):  # por si alguna vez se permitiera
        indexador.options(ignore_status=(403, 404)).indices.delete(index=nombre)
    return resultado


def main() -> None:
    pruebas = pruebas_redis() + pruebas_mongo() + pruebas_elasticsearch()
    fallidas = [p for p in pruebas if not p.ok]
    lineas = [
        '# Evidencia del control de acceso',
        '',
        f'Generado por `backend/scripts/verificar_permisos.py` el {time.strftime("%Y-%m-%d %H:%M")} contra el '
        'sistema en marcha. Cada fila es un intento real con el usuario indicado. Lo que borraría datos (borrar '
        'el índice o colecciones de la tienda) no se ejecuta: se pregunta al motor si el usuario tendría ese '
        'privilegio.',
        '',
        f'**Resultado: {len(pruebas) - len(fallidas)} de {len(pruebas)} intentos dieron lo esperado.**',
        '',
        '| Componente | Usuario | Intento | Esperado | Obtenido | Respuesta del motor |',
        '|---|---|---|---|---|---|',
    ]
    for p in pruebas:
        marca = '' if p.ok else ' ⚠'
        detalle = p.detalle.replace('|', '\\|') or '—'
        lineas.append(f'| {p.componente} | `{p.usuario}` | {p.intento} | {p.esperado} | {p.obtenido}{marca} | {detalle} |')
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text('\n'.join(lineas) + '\n', encoding='utf-8')

    for p in pruebas:
        print(f"{'OK ' if p.ok else 'MAL'} {p.componente:13s} {p.usuario:26s} {p.intento[:52]:52s} {p.obtenido}")
    print(f'\n{len(pruebas) - len(fallidas)}/{len(pruebas)} como se esperaba. Evidencia en {SALIDA.relative_to(RAIZ)}')
    sys.exit(1 if fallidas else 0)


if __name__ == '__main__':
    main()
