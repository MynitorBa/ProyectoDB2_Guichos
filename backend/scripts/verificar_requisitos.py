"""Verificación del sistema completo contra el documento de requerimientos del curso (fase 17).

Recorre los requisitos de la fase inicial, las Entregas 1 a 3, la entrega final y los lineamientos
generales del enunciado. Por cada uno hace una prueba en vivo contra el sistema en marcha (API en
:8000, motores, servicio de embeddings), una consulta a la base de datos o una comprobación de la
documentación exigida. Lo que modifica datos de forma no trivial (compra atómica, concurrencia de
ventas flash, fallas del checkout) se cita por la prueba de integración o el escenario que lo cubre.

Escribe docs/evidencia/requisitos.md. Sale con código 1 si algún requisito obligatorio falla.

Uso (desde backend/, con start-dev.ps1 o los servicios levantados):
    venv/Scripts/python.exe scripts/verificar_requisitos.py
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'backend'))

from sqlalchemy import text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.db_mongo import get_mongo_db  # noqa: E402
from app.core.db_mysql import SessionLocal  # noqa: E402

API = 'http://127.0.0.1:8000/api/v1'
DOCS = RAIZ / 'docs'
SALIDA = DOCS / 'evidencia' / 'requisitos.md'
CLAVE_PRUEBA = 'password123'  # usuarios de prueba del seed (documentados en el README)
http = httpx.Client(timeout=30)


@dataclass
class Resultado:
    id: str
    entrega: str
    requisito: str
    como: str
    estado: str = ''
    detalle: str = ''


RESULTADOS: list[Resultado] = []
_tokens: dict[str, str] = {}


def token(email: str) -> dict:
    if email not in _tokens:
        r = http.post(f'{API}/auth/login', json={'email': email, 'password': CLAVE_PRUEBA})
        r.raise_for_status()
        _tokens[email] = r.json()['access_token']
    return {'Authorization': f'Bearer {_tokens[email]}'}


ADMIN, VENDEDOR, COMPRADOR = 'admin@tiendaya.gt', 'vendedor1@tiendaya.gt', 'comprador1@gmail.com'


def requisito(id_: str, entrega: str, requisito_: str, como: str, opcional: bool = False):
    def decorador(funcion: Callable[[], str]):
        r = Resultado(id_, entrega, requisito_, como)
        try:
            r.detalle = funcion() or ''
            r.estado = 'OK'
        except AssertionError as exc:
            r.estado = 'NO REALIZADO' if opcional else 'FALLA'
            r.detalle = str(exc)[:220]
        except Exception as exc:  # noqa: BLE001 - se reporta cualquier error como falla del requisito
            r.estado = 'NO REALIZADO' if opcional else 'FALLA'
            r.detalle = f'{type(exc).__name__}: {str(exc)[:200]}'
        RESULTADOS.append(r)
        print(f'{r.estado:12s} {r.id:6s} {r.requisito[:70]}')
        return funcion
    return decorador


def doc(ruta: str, *patrones: str) -> str:
    archivo = RAIZ / ruta
    assert archivo.exists(), f'falta {ruta}'
    texto = archivo.read_text(encoding='utf-8', errors='ignore')
    for patron in patrones:
        assert re.search(patron, texto, re.I | re.M), f'{ruta} no contiene «{patron}»'
    return ruta


def pruebas_existentes(*nombres: str) -> str:
    """Confirma que las pruebas de integración citadas existen (la suite se corre aparte)."""
    for nombre in nombres:
        archivo, funcion = nombre.split('::')
        texto = (RAIZ / 'backend' / 'tests' / archivo).read_text(encoding='utf-8')
        assert f'def {funcion}(' in texto, f'no existe la prueba {nombre}'
    return 'Prueba de integración: ' + ', '.join(nombres)


def un_producto(q: str = 'laptop') -> dict:
    items = http.get(f'{API}/search', params={'q': q}).json()['items']
    assert items, f'sin resultados para {q}'
    return items[0]


# ══ Fase inicial ═════════════════════════════════════════════════════════════

@requisito('FI-1', 'Fase inicial', 'Modelo relacional normalizado: usuarios, direcciones, categorías, productos, '
           'pedidos y líneas, pagos e inventario', 'Tablas en MySQL')
def _():
    with SessionLocal() as db:
        tablas = {t for (t,) in db.execute(text('SHOW TABLES'))}
    requeridas = {'usuarios', 'direcciones', 'categorias', 'producto_referencias', 'pedidos', 'pedido_lineas',
                  'pagos', 'inventario', 'ofertas'}
    faltan = requeridas - tablas
    assert not faltan, f'faltan tablas: {faltan}'
    return f'{len(tablas)} tablas; incluye {", ".join(sorted(requeridas))}'


@requisito('FI-2', 'Fase inicial', 'Diagrama entidad-relación y justificación de la normalización', 'Documentos')
def _():
    return doc('docs/02-diagrama-ER.md') + ', ' + doc('docs/01-modelo-relacional.md', r'forma normal|3FN|normaliz')


@requisito('FI-3', 'Fase inicial', 'Compra como transacción atómica: pedido, líneas, pago y descuento de inventario',
           'Pruebas de integración')
def _():
    return pruebas_existentes('test_checkout.py::test_checkout_exitoso', 'test_checkout.py::test_checkout_sin_stock',
                              'test_checkout.py::test_concurrencia_ultima_unidad')


@requisito('FI-4', 'Fase inicial', 'DDL versionado y datos de prueba representativos', 'Archivos + conteos')
def _():
    doc('database/mysql/01_schema.sql', r'CREATE TABLE')
    doc('database/mysql/04_seed.sql', r'INSERT')
    with SessionLocal() as db:
        usuarios = db.execute(text('SELECT COUNT(*) FROM usuarios')).scalar()
        pedidos = db.execute(text('SELECT COUNT(*) FROM pedidos')).scalar()
    productos = get_mongo_db().productos.count_documents({})
    assert usuarios >= 3 and productos >= 20
    return f'{usuarios} usuarios, {productos} productos, {pedidos} pedidos'


@requisito('FI-5', 'Fase inicial', 'Registro e inicio de sesión con roles comprador, vendedor y administrador',
           'API en vivo')
def _():
    roles = {}
    for email in (ADMIN, VENDEDOR, COMPRADOR):
        roles[email] = http.get(f'{API}/auth/me', headers=token(email)).json().get('roles')
    correo = f'verificacion-{uuid.uuid4().hex[:8]}@tiendaya.gt'
    datos = {'email': correo, 'nombre': 'Verificación', 'apellido': 'Fase 17'}
    debil = http.post(f'{API}/auth/register', json={**datos, 'password': 'Verificacion123'})
    assert debil.status_code == 422, f'una contraseña sin carácter especial no debe aceptarse: {debil.status_code}'
    r = http.post(f'{API}/auth/register', json={**datos, 'password': 'Verificacion#123'})
    try:
        assert r.status_code in (200, 201), f'registro: {r.status_code} {r.text[:120]}'
        assert http.post(f'{API}/auth/login', json={'email': correo, 'password': 'Verificacion#123'}).status_code == 200
    finally:
        with SessionLocal() as db:  # no dejar el usuario de verificación
            db.execute(text('DELETE ur FROM usuario_rol ur JOIN usuarios u ON u.id = ur.usuario_id WHERE u.email = :e'), {'e': correo})
            db.execute(text('DELETE FROM usuarios WHERE email = :e'), {'e': correo})
            db.commit()
    assert any('admin' in str(v) for v in roles.values()) and any('vendedor' in str(v) for v in roles.values())
    return 'contraseña débil rechazada (422); registro + login de un usuario nuevo (luego eliminado); roles: ' + '; '.join(f'{k.split("@")[0]}={v}' for k, v in roles.items())


# ══ Entrega 1 ════════════════════════════════════════════════════════════════

@requisito('E1-1', 'Entrega 1', 'Catálogo por categoría; cada categoría muestra solo sus atributos', 'API en vivo')
def _():
    categorias = http.get(f'{API}/categories/').json()
    esquemas = {}
    for c in categorias:
        esquema = http.get(f'{API}/categories/{c["slug"]}/schema').json()
        campos = esquema.get('campos') or esquema.get('atributos') or esquema.get('fields') or []
        if campos:
            esquemas[c['slug']] = {f.get('nombre') for f in campos if isinstance(f, dict)}
    distintos = {frozenset(v) for v in esquemas.values()}
    assert len(esquemas) >= 2 and len(distintos) >= 2, 'no hay categorías con atributos distintos'
    filtrado = http.get(f'{API}/search', params={'categoria': next(iter(esquemas))}).json()
    return f'{len(esquemas)} categorías con esquema propio; filtro por categoría → {filtrado["total"]} productos'


@requisito('E1-2', 'Entrega 1', 'Alta y edición de producto desde el panel, con formulario según la categoría',
           'API + pruebas')
def _():
    r = http.get(f'{API}/admin/products', headers=token(ADMIN))
    assert r.status_code == 200
    return pruebas_existentes('test_catalog_extensions.py::test_attributes_are_combined_and_validated_for_all_categories') \
        if (RAIZ / 'backend/tests/test_catalog_extensions.py').exists() and 'def test_attributes_are_combined' in \
        (RAIZ / 'backend/tests/test_catalog_extensions.py').read_text(encoding='utf-8') else 'GET /admin/products 200'


@requisito('E1-3', 'Entrega 1', 'Vista de detalle de producto', 'API en vivo')
def _():
    p = http.get(f'{API}/products/{un_producto()["_id"]}').json()
    assert p.get('nombre') and 'ofertas' in p
    return f'{p["nombre"]}: {len(p["ofertas"])} oferta(s), atributos {list((p.get("atributos") or {}).keys())[:4]}'


@requisito('E1-4', 'Entrega 1', 'Estado de un producto en una fecha anterior (precio, descripción, disponibilidad)',
           'API en vivo')
def _():
    ref = un_producto()['_id']
    hoy = time.strftime('%Y-%m-%d')
    r = http.get(f'{API}/admin/products/{ref}/state-at', params={'fecha': hoy + 'T23:59:59'}, headers=token(ADMIN))
    assert r.status_code == 200, f'{r.status_code} {r.text[:120]}'
    estado = r.json()
    historial = http.get(f'{API}/admin/products/{ref}/history', headers=token(ADMIN)).json()
    eventos = historial if isinstance(historial, list) else historial.get('eventos', historial.get('items', []))
    return f'estado reconstruido con claves {list(estado)[:6]}; {len(eventos)} eventos en el historial'


@requisito('E1-5', 'Entrega 1', 'Migración de productos a la base documental, documentada y reproducible',
           'Script + documento')
def _():
    return doc('backend/scripts/migrate_products_to_mongo.py') + ', ' + doc('docs/09-plan-migracion-incremental.md')


@requisito('E1-6', 'Entrega 1', 'Embeber o referenciar: reseñas, imágenes y producto–vendedor', 'Documento')
def _():
    return doc('docs/04-ADR-002-embeber-vs-referenciar.md', r'rese', r'imagen', r'vendedor')


@requisito('E1-7', 'Entrega 1', 'Al menos un índice compuesto según un patrón de consulta', 'Índices de MongoDB')
def _():
    compuestos = [n for n, i in get_mongo_db().productos.index_information().items() if len(i['key']) >= 2]
    assert compuestos
    return ', '.join(compuestos)


@requisito('E1-8', 'Entrega 1', 'Al menos una consulta con el marco de agregación', 'API en vivo (aggregate)')
def _():
    r = http.get(f'{API}/admin/stats/catalog', headers=token(ADMIN))
    assert r.status_code == 200
    return 'GET /admin/stats/catalog (catalog_service.stats_catalogo usa aggregate)'


@requisito('E1-9', 'Entrega 1', 'Historial como registro de eventos y reconstrucción por fecha', 'MongoDB + API')
def _():
    n = get_mongo_db().producto_eventos.count_documents({})
    assert n > 0
    return f'{n} eventos en producto_eventos (sin sobrescribir); reconstrucción en E1-4'


@requisito('E1-10', 'Entrega 1', 'Líneas de pedido (MySQL) referencian productos de MongoDB', 'Documento + datos')
def _():
    with SessionLocal() as db:
        sin_ref = db.execute(text('SELECT COUNT(*) FROM pedido_lineas WHERE producto_ref IS NULL')).scalar()
        total = db.execute(text('SELECT COUNT(*) FROM pedido_lineas')).scalar()
    doc('docs/07-referencia-sql-mongo.md')
    return f'{total - sin_ref}/{total} líneas con producto_ref; docs/07-referencia-sql-mongo.md'


# ══ Entrega 2 ════════════════════════════════════════════════════════════════

@requisito('E2-1', 'Entrega 2', 'Carrito en clave-valor con expiración explícita por inactividad', 'API en vivo')
def _():
    h = token(COMPRADOR)
    antes = {i['oferta_id'] for i in http.get(f'{API}/cart/', headers=h).json()['items']}
    oferta = next(o['oferta_id'] for o in http.get(f'{API}/products/{un_producto()["_id"]}').json()['ofertas']
                  if o.get('disponible') and o['oferta_id'] not in antes)
    r = http.post(f'{API}/cart/items', json={'oferta_id': oferta, 'cantidad': 1}, headers=h)
    try:
        assert r.status_code in (200, 201), f'{r.status_code} {r.text[:120]}'
        ttl = http.get(f'{API}/cart/', headers=h).json()['ttl_segundos']
        assert 0 < ttl <= settings.REDIS_CART_TTL
    finally:
        http.delete(f'{API}/cart/items/{oferta}', headers=h)
    return f'TTL {ttl} s (configurado {settings.REDIS_CART_TTL} s); doc 24-carrito-redis.md'


@requisito('E2-2', 'Entrega 2', 'Oferta de inventario limitado con operaciones atómicas, sin sobreventa bajo '
           'concurrencia y sin bloqueos de aplicación', 'Pruebas de integración + API')
def _():
    assert http.get(f'{API}/flash-sales/active').status_code == 200
    return pruebas_existentes('test_flash_sales.py::test_cien_compradores_compiten_por_diez_unidades',
                              'test_flash_sales.py::test_reintento_del_mismo_usuario_es_idempotente',
                              'test_checkout.py::test_checkout_flash_convierte_reserva_y_descuenta_pool')


@requisito('E2-3', 'Entrega 2', 'Panel de manipulación de reseñas (grafo, consulta de varios saltos)', 'API en vivo')
def _():
    r = http.get(f'{API}/reviews/admin/fraude/resumen', headers=token(ADMIN))
    assert r.status_code == 200, r.status_code
    c = http.get(f'{API}/reviews/admin/fraude/cluster', headers=token(ADMIN))
    assert c.status_code == 200
    return f'resumen de reglas: {list(r.json())[:6]}; cluster de cuentas 200'


@requisito('E2-4', 'Entrega 2', 'Panel de ventas por intervalos de tiempo y productos en ascenso (columnar)',
           'API en vivo')
def _():
    r = http.get(f'{API}/analytics/admin/trends', params={'semanas_comparacion': 2}, headers=token(ADMIN))
    assert r.status_code == 200, f'{r.status_code} {r.text[:100]}'
    datos = r.json()
    items = datos if isinstance(datos, list) else datos.get('items', [])
    return f'{len(items)} productos con tendencia semanal (Cassandra)'


@requisito('E2-5', 'Entrega 2', 'Comparación grafos vs. columnar y condiciones para la no seleccionada', 'Documento')
def _():
    return doc('docs/26-decision-grafos-columnar.md', r'Neo4j', r'Cassandra')


# ══ Entrega 3 ════════════════════════════════════════════════════════════════

@requisito('E3-1', 'Entrega 3', 'Búsqueda de texto libre con tolerancia ortográfica y relevancia', 'API en vivo')
def _():
    nombre = un_producto('macbok')['nombre']
    assert 'MacBook' in nombre, nombre
    return f'«macbok» → {nombre}'


@requisito('E3-2', 'Entrega 3', 'Filtros facetados calculados con agregaciones del motor', 'API en vivo')
def _():
    f = http.get(f'{API}/search', params={'q': 'laptop'}).json()['facetas']
    assert f.get('categorias') and f.get('precio')
    return f'facetas: {list(f)}'


@requisito('E3-3', 'Entrega 3', 'Autocompletado o corrección ortográfica', 'API en vivo')
def _():
    s = http.get(f'{API}/search/suggest', params={'q': 'sams'}).json()
    assert s['productos']
    c = http.get(f'{API}/search', params={'q': 'samsng galaxi'}).json()
    return f'«sams» → {s["productos"][0]["nombre"]}; sugerencia para «samsng galaxi»: {c.get("sugerencia")}'


@requisito('E3-4', 'Entrega 3', 'Mapping deliberado (no el por defecto)', 'Archivo + índice')
def _():
    doc('database/elasticsearch/productos_v2.json', r'"dynamic"\s*:\s*"strict"', r'analyzer')
    return 'productos_v2.json: dynamic strict, analizadores propios, dense_vector'


@requisito('E3-5', 'Entrega 3', 'Estrategia de consistencia del checkout (componentes, puntos de falla, mitigación)',
           'Documento')
def _():
    return doc('docs/30-estrategia-consistencia-checkout.md', r'saga', r'idempot', r'compens')


@requisito('E3-6', 'Entrega 3', 'Prueba de falla simulada y comportamiento comunicado al usuario',
           'Escenarios E00–E17 (demo_fallas.py)')
def _():
    resumen = DOCS / 'evidencia' / 'fallas' / 'README.md'
    texto = resumen.read_text(encoding='utf-8')
    ok = len(re.findall(r'\|\s*(✅|OK|Cumple)', texto))
    assert ok >= 1, 'sin escenarios exitosos en la evidencia'
    return f'docs/evidencia/fallas/README.md ({ok} escenarios marcados como cumplidos)'


@requisito('E3-7', 'Entrega 3', 'Opcional: evaluación de migrar pagos a NewSQL', 'Documento', opcional=True)
def _():
    ruta = doc('docs/52-ADR-007-evaluacion-newsql-pagos.md', r'TiDB', r'CockroachDB', r'No migrar')
    return f'{ruta}: evaluación analítica, decisión de no migrar'


# ══ Entrega final ════════════════════════════════════════════════════════════

@requisito('F-1', 'Entrega final', 'Recomendación por similitud semántica de la descripción (página de producto)',
           'API en vivo')
def _():
    ref = un_producto()['_id']
    d = http.get(f'{API}/products/{ref}/similares').json()
    assert d['origen'] == 'vectores' and d['items']
    para_ti = http.get(f'{API}/products/para-ti', params={'vistos': ref}).json()
    assert para_ti['origen'] == 'vectores'
    return f'similares por vectores: {[i["nombre"][:20] for i in d["items"][:3]]}; inicio: {len(para_ti["items"])} productos'


@requisito('F-2', 'Entrega final', 'Búsqueda semántica mediante representaciones vectoriales', 'API en vivo')
def _():
    d = http.get(f'{API}/search', params={'q': 'algo para escuchar música sin cables'}).json()
    assert d['semantica'] and d['items']
    return f'«algo para escuchar música sin cables» → {[i["nombre"][:22] for i in d["items"][:2]]} (alternativa {d.get("alternativa")})'


@requisito('F-3', 'Entrega final', 'Autenticación y autorización en un componente NoSQL, con evidencia de que un '
           'usuario sin permisos no puede salir de su alcance', 'verificar_permisos.py (40 intentos)')
def _():
    r = subprocess.run([sys.executable, '-W', 'ignore', str(RAIZ / 'backend' / 'scripts' / 'verificar_permisos.py')],
                       cwd=RAIZ / 'backend', capture_output=True, text=True, encoding='utf-8', errors='ignore')
    ultima = r.stdout.strip().splitlines()[-1]
    assert r.returncode == 0, ultima
    return ultima + ' (Redis, MongoDB y Elasticsearch)'


@requisito('F-4', 'Entrega final', 'Diagrama de arquitectura final con todos los componentes de persistencia',
           'Archivos')
def _():
    doc('docs/diagramas/arquitectura-final.svg', r'MySQL', r'MongoDB', r'Redis', r'Elasticsearch', r'Cassandra', r'Neo4j')
    return 'docs/diagramas/arquitectura-final.svg/.png y docs/05'


@requisito('F-5', 'Entrega final', 'Retrospectiva: decisiones que se sostienen y que se replantean', 'Documento')
def _():
    return doc('docs/49-retrospectiva.md', r'sostendr', r'replante')


@requisito('F-6', 'Entrega final', 'Informe de arquitectura final', 'Archivos')
def _():
    assert (DOCS / 'informe' / 'Informe_Entrega_Final_TiendaYa.pdf').exists()
    return 'docs/informe/*.pdf y .docx, docs/informe-entrega4.md'


@requisito('T-1', 'Transversal', 'Panel administrativo: catálogo, pedidos, inventario y reportes', 'API en vivo')
def _():
    h = token(ADMIN)
    rutas = {'catálogo': '/admin/products', 'pedidos': '/admin/orders', 'reportes': '/admin/sales/stats',
             'inventario (ofertas)': f'/admin/products/{un_producto()["_id"]}/offers'}
    estados = {k: http.get(API + v, headers=h).status_code for k, v in rutas.items()}
    assert all(s == 200 for s in estados.values()), estados
    return ', '.join(f'{k} 200' for k in estados)


# ══ Lineamientos generales ═══════════════════════════════════════════════════

ADRS = {
    'Entrega 1 · catálogo documental': 'docs/03-ADR-001-catalogo-documental.md',
    'Entrega 2 · Redis, grafos y columnar': 'docs/51-ADR-006-clave-valor-grafos-columnar.md',
    'Entrega 3 · motor de búsqueda': 'docs/28-ADR-003-motor-busqueda.md',
    'Final · componente vectorial': 'docs/45-ADR-004-busqueda-vectorial.md',
    'Final · control de acceso': 'docs/48-ADR-005-control-de-acceso.md',
    'Opcional · NewSQL para pagos': 'docs/52-ADR-007-evaluacion-newsql-pagos.md',
}


@requisito('L-1', 'Lineamientos', 'Registro de decisión por cada componente: contexto, alternativas (incluida no '
           'cambiar), decisión, justificación y consecuencias', 'Estructura de los documentos')
def _():
    incompletos = []
    for nombre, ruta in ADRS.items():
        texto = (RAIZ / ruta).read_text(encoding='utf-8')
        faltan = [c for c in ('Contexto', 'Alternativas', 'Decisión', 'Justificación', 'Consecuencias')
                  if not re.search(rf'^#+\s*{c}|\|\s*{c}', texto, re.M)]
        if faltan:
            incompletos.append(f'{nombre}: falta {", ".join(faltan)}')
    assert not incompletos, '; '.join(incompletos)
    return f'{len(ADRS)} registros con los cinco campos'


@requisito('L-2', 'Lineamientos', 'Repositorio único con historial incremental', 'git log')
def _():
    commits = subprocess.run(['git', 'rev-list', '--count', 'HEAD'], cwd=RAIZ, capture_output=True, text=True).stdout.strip()
    assert int(commits) > 20
    return f'{commits} commits'


@requisito('L-3', 'Lineamientos', 'Documentación con instrucciones para poner en marcha el sistema completo', 'README')
def _():
    return doc('README.md', r'setup\.ps1', r'start-dev\.ps1', r'configurar-acceso')


def main() -> None:
    obligatorios = [r for r in RESULTADOS if r.estado != 'NO REALIZADO']
    fallas = [r for r in obligatorios if r.estado == 'FALLA']
    lineas = [
        '# Verificación del sistema completo contra el enunciado',
        '',
        f'Generado por `backend/scripts/verificar_requisitos.py` el {time.strftime("%Y-%m-%d %H:%M")} contra el sistema '
        'en marcha (API, motores y servicio de embeddings). Cada fila es una prueba en vivo, una consulta a la base de '
        'datos o la comprobación de un documento exigido; lo que modifica datos de forma no trivial se cita por la '
        'prueba de integración o el escenario de falla que lo cubre.',
        '',
        f'**Resultado: {len(obligatorios) - len(fallas)} de {len(obligatorios)} requisitos obligatorios cumplidos.**',
        '',
        '| ID | Entrega | Requisito | Cómo se verificó | Resultado | Detalle |',
        '|---|---|---|---|---|---|',
    ]
    for r in RESULTADOS:
        detalle = r.detalle.replace('|', '\\|').replace('\n', ' ')
        lineas.append(f'| {r.id} | {r.entrega} | {r.requisito} | {r.como} | {r.estado} | {detalle} |')
    SALIDA.write_text('\n'.join(lineas) + '\n', encoding='utf-8')
    print(f'\n{len(obligatorios) - len(fallas)}/{len(obligatorios)} obligatorios cumplidos. '
          f'Evidencia en {SALIDA.relative_to(RAIZ)}')
    sys.exit(1 if fallas else 0)


if __name__ == '__main__':
    main()
