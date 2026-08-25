from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.database import Database

from app.core.config import settings

_client: MongoClient | None = None


def get_mongo_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(settings.MONGO_URI)
    return _client


def get_mongo_db() -> Database:
    return get_mongo_client()[settings.MONGO_DB]


def ensure_indexes(db: Database) -> None:
    """
    Crea los índices de MongoDB al arrancar la aplicación (idempotente).

    Índices de la colección `productos`:
    - Índice compuesto (categoria.slug, disponible, precio): soporta el patrón
      de consulta más frecuente del catálogo — filtrar por categoría y
      disponibilidad, luego ordenar por precio ascendente o descendente.
      Evita un COLLSCAN en cada request del catálogo público.
    - Índice de texto en `nombre` y `descripcion`: soporte para búsqueda
      fulltext básica desde el endpoint de catálogo.

    Índices de la colección `producto_eventos`:
    - Índice compuesto (producto_id, timestamp): acelera la reconstrucción
      de estado histórico, que necesita todos los eventos de un producto
      ordenados cronológicamente — el patrón exacto de este índice.
    """
    # ── productos ─────────────────────────────────────────────────────────────
    db.productos.create_index(
        [('categoria.slug', ASCENDING), ('disponible', ASCENDING), ('precio', ASCENDING)],
        name='idx_categoria_disponible_precio',
        background=True,
    )
    db.productos.create_index(
        [('nombre', 'text'), ('descripcion', 'text')],
        name='idx_texto_nombre_descripcion',
        default_language='spanish',
        background=True,
    )

    # ── producto_eventos ──────────────────────────────────────────────────────
    db.producto_eventos.create_index(
        [('producto_id', ASCENDING), ('timestamp', ASCENDING)],
        name='idx_producto_timestamp',
        background=True,
    )
    db.productos.create_index(
        [('categorias.slug', ASCENDING), ('estado', ASCENDING)],
        name='idx_categorias_estado',
        background=True,
    )
    db.producto_eventos.create_index(
        [('outbox_id', ASCENDING)],
        name='uidx_evento_outbox',
        unique=True,
        sparse=True,
        background=True,
    )


def close_mongo():
    global _client
    if _client:
        _client.close()
        _client = None
