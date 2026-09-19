"""CRUD de configuración de tienda en MongoDB."""

from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

COLLECTION = 'tiendas_config'

DEFAULT_TEMA: dict[str, Any] = {
    'color_primario': '#0288D1',
    'color_fondo': '#ffffff',
    'color_texto': '#1a1a1a',
    'color_acento': '#f59e0b',
    'fuente_titulos': 'Inter',
    'fuente_cuerpo': 'Inter',
    'radio_bordes': 'md',
    'logo_url': '',
    'logo_tamano': 'md',
    'logo_posicion': 'top-left',
    'estilo_boton': 'degradado',
}

DEFAULT_SECCIONES: list[dict[str, Any]] = [
    {
        'id': 'hero-default',
        'tipo': 'hero',
        'visible': True,
        'config': {
            'titulo': 'Bienvenido a nuestra tienda',
            'subtitulo': 'Encuentra los mejores productos al mejor precio.',
            'imagen_url': '',
            'alineacion': 'center',
            'boton_texto': 'Ver productos',
            'overlay_opacidad': 40,
            'altura': 'md',
        },
    },
    {
        'id': 'productos-default',
        'tipo': 'productos',
        'visible': True,
        'config': {
            'titulo': 'Nuestros productos',
            'cantidad': 8,
        },
    },
]


def get_config(mongo_db: Database, vendedor_id: int) -> dict | None:
    return mongo_db[COLLECTION].find_one({'vendedor_id': vendedor_id}, {'_id': 0})


def save_config(mongo_db: Database, vendedor_id: int, payload: dict) -> dict:
    tema = {**DEFAULT_TEMA, **payload.get('tema', {})}
    doc = {
        'vendedor_id': vendedor_id,
        'tema': tema,
        'secciones': payload.get('secciones', DEFAULT_SECCIONES),
        'actualizado_en': datetime.now(timezone.utc).isoformat(),
    }
    mongo_db[COLLECTION].replace_one({'vendedor_id': vendedor_id}, doc, upsert=True)
    return doc
