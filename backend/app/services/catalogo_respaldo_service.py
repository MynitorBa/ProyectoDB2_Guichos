"""Copia del catálogo de MongoDB en MySQL y lectura con respaldo (plan B de MongoDB).

**Escritura.** Los documentos de ``productos`` y ``producto_variantes`` se
copian completos (JSON extendido de BSON: conserva ObjectId y fechas) en la
tabla ``catalogo_respaldo``. La copia la mantiene el outbox (destino
``catalogo``, por estado y no por delta) y una reconciliación periódica que
detecta documentos nuevos, editados o eliminados.

**Lectura.** ``productos``, ``producto`` y ``productos_por_ids`` intentan
MongoDB; si no responde (o su circuito está abierto) leen la copia de MySQL y,
para un producto que aún no esté copiado, el documento de Elasticsearch.
Devuelven también si se usó el respaldo, para avisarlo al usuario. El precio y
el stock nunca salen de aquí: los sigue poniendo MySQL al enriquecer.
"""

from __future__ import annotations

import logging
import re

from bson import ObjectId, json_util
from bson.errors import InvalidId
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ExecutionTimeout, ServerSelectionTimeoutError
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.core import salud
from app.core.db_mysql import SessionLocal
from app.core.time import utc_now

logger = logging.getLogger(__name__)

ERRORES_MONGO = (ConnectionFailure, ExecutionTimeout)
COLECCIONES = ('productos', 'producto_variantes')


# ── Escritura de la copia ─────────────────────────────────────────────────────

def _guardar(db: Session, coleccion: str, doc: dict) -> None:
    db.execute(text("""
        INSERT INTO catalogo_respaldo
          (coleccion, ref, producto_ref, estado, documento, actualizado_mongo, copiado_en)
        VALUES (:c, :r, :p, :e, :d, :a, :ahora)
        ON DUPLICATE KEY UPDATE producto_ref = VALUES(producto_ref), estado = VALUES(estado),
          documento = VALUES(documento), actualizado_mongo = VALUES(actualizado_mongo),
          copiado_en = VALUES(copiado_en)
    """), {
        'c': coleccion, 'r': str(doc['_id']),
        'p': str(doc['producto_ref']) if doc.get('producto_ref') else None,
        'e': doc.get('estado'), 'd': json_util.dumps(doc),
        'a': doc.get('fecha_actualizacion'), 'ahora': utc_now(),
    })


def _borrar(db: Session, coleccion: str, ref: str) -> None:
    db.execute(text('DELETE FROM catalogo_respaldo WHERE coleccion = :c AND ref = :r'),
               {'c': coleccion, 'r': ref})


def copiar_producto(mongo: Database, db: Session, producto_ref: str) -> None:
    """Copia el estado actual del producto y sus variantes; si ya no existe, lo retira.

    Lee de MongoDB y escribe en la transacción ``db`` del llamador (sin commit).
    Repetirlo da el mismo resultado: idempotente e independiente del orden.
    """
    try:
        oid = ObjectId(producto_ref)
    except InvalidId:
        return
    doc = mongo.productos.find_one({'_id': oid})
    if doc:
        _guardar(db, 'productos', doc)
    else:
        _borrar(db, 'productos', producto_ref)
    _actualizar_autocompletado(producto_ref, doc)
    variantes = list(mongo.producto_variantes.find({'producto_ref': producto_ref}))
    vigentes = {str(v['_id']) for v in variantes}
    for variante in variantes:
        _guardar(db, 'producto_variantes', variante)
    copiadas = db.execute(text("""
        SELECT ref FROM catalogo_respaldo WHERE coleccion = 'producto_variantes' AND producto_ref = :p
    """), {'p': producto_ref}).scalars().all()
    for ref in set(copiadas) - vigentes:
        _borrar(db, 'producto_variantes', ref)


def _actualizar_autocompletado(producto_ref: str, doc: dict | None) -> None:
    """Refleja el producto en el autocompletado de respaldo de Redis (sin fallar).

    Si Redis no responde, la reconstrucción periódica lo pone al día después.
    """
    if not salud.disponible('redis'):
        return
    try:
        from app.core.db_redis import get_redis
        from app.services import autocompletado_respaldo_service as autocompletado
        autocompletado.actualizar(get_redis(), producto_ref, doc)
    except Exception as exc:  # noqa: BLE001 - el autocompletado de respaldo es opcional
        logger.warning('No se actualizó el autocompletado de respaldo de %s: %s', producto_ref, exc)


def reconstruir_autocompletado() -> int:
    """Rehace el autocompletado de respaldo de Redis con los productos activos de la copia."""
    from app.core.db_redis import get_redis
    from app.services import autocompletado_respaldo_service as autocompletado
    return autocompletado.reconstruir(get_redis(), productos_copiados(estado='activo'))


def productos_copiados(*, estado: str | None = None) -> list[dict]:
    """Documentos de productos tal como están en la copia de MySQL."""
    with SessionLocal() as db:
        sql = "SELECT documento FROM catalogo_respaldo WHERE coleccion = 'productos'"
        if estado:
            sql += ' AND estado = :estado'
        return [_cargar(d) for d in db.execute(text(sql), {'estado': estado}).scalars()]


def reconciliar(mongo: Database, db: Session) -> dict:
    """Copia lo nuevo o editado desde la última copia y retira lo que ya no existe.

    Red de seguridad para cambios del catálogo que no dejaron evento en el
    outbox (por ejemplo, una caída entre la escritura en MongoDB y el encolado).
    """
    resumen = {'copiados': 0, 'retirados': 0}
    for coleccion in COLECCIONES:
        copiados = {
            ref: actualizado for ref, actualizado in db.execute(text(
                'SELECT ref, actualizado_mongo FROM catalogo_respaldo WHERE coleccion = :c'
            ), {'c': coleccion}).all()
        }
        vistos = set()
        for doc in mongo[coleccion].find({}):
            ref = str(doc['_id'])
            vistos.add(ref)
            actualizado = doc.get('fecha_actualizacion')
            if ref not in copiados or (actualizado and (copiados[ref] is None or actualizado > copiados[ref])):
                _guardar(db, coleccion, doc)
                resumen['copiados'] += 1
        for ref in set(copiados) - vistos:
            _borrar(db, coleccion, ref)
            resumen['retirados'] += 1
    return resumen


# ── Lectura con respaldo ──────────────────────────────────────────────────────

def _ejecutar(en_mongo, en_respaldo):
    """Intenta MongoDB y, si no responde, el respaldo. Devuelve (resultado, desde_respaldo)."""
    if salud.disponible('mongo'):
        try:
            resultado = en_mongo()
            salud.registrar_exito('mongo')
            return resultado, False
        except ERRORES_MONGO as exc:
            # Sin servidor alcanzable el circuito se abre de una vez: las siguientes
            # lecturas van directo a la copia en lugar de esperar el timeout.
            salud.registrar_falla('mongo', exc, confirmada=isinstance(exc, ServerSelectionTimeoutError))
            logger.warning('MongoDB no respondió; el catálogo se lee de su copia en MySQL: %s', exc)
    return en_respaldo(), True


def _cargar(fila) -> dict:
    return json_util.loads(fila if isinstance(fila, str) else json_util.dumps(fila))


def _categorias(doc: dict) -> set[str]:
    """Como el filtro de MongoDB: la categoría principal y la lista de categorías."""
    categorias = list(doc.get('categorias') or []) + ([doc['categoria']] if doc.get('categoria') else [])
    return {c.get('slug') for c in categorias if isinstance(c, dict)}


def _respaldo_productos(*, estado: str | None, categoria_slug: str | None, q: str | None) -> list[dict]:
    docs = productos_copiados(estado=estado)
    if not docs:
        docs = _productos_elasticsearch(estado=estado)
    if categoria_slug:
        docs = [d for d in docs if categoria_slug in _categorias(d)]
    if q:
        patron = re.compile(re.escape(q.strip()), re.IGNORECASE)
        docs = [d for d in docs if patron.search(d.get('nombre') or '') or patron.search(d.get('sku') or '')]
    return docs


def productos(mongo: Database, filtro: dict, *, estado: str | None, categoria_slug: str | None,
              q: str | None) -> tuple[list[dict], bool]:
    """Documentos del listado. ``filtro`` es el de MongoDB; los demás argumentos lo
    describen para poder aplicarlo también sobre la copia."""
    return _ejecutar(
        lambda: list(mongo.productos.find(filtro)),
        lambda: _respaldo_productos(estado=estado, categoria_slug=categoria_slug, q=q),
    )


def producto(mongo: Database, producto_id: str) -> tuple[dict | None, bool]:
    """Un producto por ObjectId o, si no lo es, por SKU."""
    def en_mongo():
        try:
            return mongo.productos.find_one({'_id': ObjectId(producto_id)})
        except InvalidId:
            return mongo.productos.find_one({'sku': producto_id})

    def en_respaldo():
        with SessionLocal() as db:
            fila = db.execute(text("""
                SELECT documento FROM catalogo_respaldo
                WHERE coleccion = 'productos'
                  AND (ref = :id OR JSON_UNQUOTE(JSON_EXTRACT(documento, '$.sku')) = :id)
                LIMIT 1
            """), {'id': producto_id}).scalar()
        if fila is not None:
            return _cargar(fila)
        if not ObjectId.is_valid(producto_id):
            return None
        encontrados = _productos_elasticsearch(ids=[producto_id])
        return encontrados[0] if encontrados else None

    return _ejecutar(en_mongo, en_respaldo)


def productos_por_ids(mongo: Database, ids: list[str]) -> tuple[dict[str, dict], bool]:
    """Documentos por ObjectId (texto), como diccionario id → documento."""
    validos = [i for i in ids if ObjectId.is_valid(i)]

    def en_mongo():
        return {str(d['_id']): d for d in mongo.productos.find({'_id': {'$in': [ObjectId(i) for i in validos]}})}

    def en_respaldo():
        if not validos:
            return {}
        with SessionLocal() as db:
            filas = db.execute(text("""
                SELECT ref, documento FROM catalogo_respaldo
                WHERE coleccion = 'productos' AND ref IN :ids
            """).bindparams(bindparam('ids', expanding=True)), {'ids': validos}).all()
        docs = {ref: _cargar(doc) for ref, doc in filas}
        faltantes = [i for i in validos if i not in docs]
        for doc in _productos_elasticsearch(ids=faltantes) if faltantes else []:
            docs[str(doc['_id'])] = doc
        return docs

    return _ejecutar(en_mongo, en_respaldo)


def variantes(mongo: Database, refs: list[str]) -> dict[str, dict]:
    """Documentos de variantes por ObjectId (texto)."""
    validos = [r for r in refs if ObjectId.is_valid(r)]

    def en_mongo():
        return {
            str(d['_id']): d
            for d in mongo.producto_variantes.find({'_id': {'$in': [ObjectId(r) for r in validos]}})
        }

    def en_respaldo():
        if not validos:
            return {}
        with SessionLocal() as db:
            filas = db.execute(text("""
                SELECT ref, documento FROM catalogo_respaldo
                WHERE coleccion = 'producto_variantes' AND ref IN :refs
            """).bindparams(bindparam('refs', expanding=True)), {'refs': validos}).all()
        return {ref: _cargar(doc) for ref, doc in filas}

    return _ejecutar(en_mongo, en_respaldo)[0]


# ── Último recurso: el documento de Elasticsearch ────────────────────────────

def _desde_indice(fuente: dict) -> dict:
    """Convierte un documento del índice de búsqueda a la forma del catálogo.

    Es parcial (una imagen, sin historial), pero alcanza para listar y mostrar
    un producto que todavía no llegó a la copia de MySQL.
    """
    categorias = fuente.get('categorias') or []
    atributos = {
        a['nombre']: a['valor'] for a in fuente.get('atributos') or []
        if a.get('nombre') and a.get('origen') != 'variante'
    }
    return {
        '_id': ObjectId(fuente['producto_id']),
        'nombre': fuente.get('nombre'),
        'descripcion': fuente.get('descripcion'),
        'sku': fuente.get('sku'),
        'estado': fuente.get('estado'),
        'categoria': categorias[0] if categorias else None,
        'categorias': categorias,
        'imagenes': [fuente['imagen']] if fuente.get('imagen') else [],
        'atributos': atributos,
    }


def _productos_elasticsearch(*, ids: list[str] | None = None, estado: str | None = None) -> list[dict]:
    if not salud.disponible('elasticsearch'):
        return []
    try:
        from app.core.config import settings
        from app.core.db_elastic import get_es
        consulta = {'ids': {'values': ids}} if ids is not None else (
            {'term': {'estado': estado}} if estado else {'match_all': {}}
        )
        respuesta = get_es().search(index=settings.ES_INDEX_ALIAS, query=consulta, size=1000,
                                    source_excludes=['vector'])
        return [_desde_indice(hit['_source']) for hit in respuesta['hits']['hits']]
    except Exception as exc:  # noqa: BLE001 - último recurso: sin índice, sin documentos
        logger.warning('Tampoco se pudo leer el catálogo desde Elasticsearch: %s', exc)
        return []
