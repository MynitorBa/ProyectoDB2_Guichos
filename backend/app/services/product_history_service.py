"""
Servicio de historial de productos por eventos (event sourcing).

Estrategia: replay completo desde el evento PRODUCTO_CREADO hasta la fecha dada.
Se eligió replay completo porque:
  - El volumen de eventos por producto es bajo (decenas, no miles).
  - Un snapshot añadiría complejidad sin ganancia real a esta escala.
  - El replay completo garantiza auditabilidad perfecta: el estado en cualquier
    fecha se puede verificar manualmente leyendo la secuencia de eventos.

Si el sistema creciera a miles de eventos por producto, se implementaría
snapshot periódico (por ejemplo, cada 100 eventos) y replay desde el snapshot
más reciente anterior a la fecha solicitada.
"""
from datetime import datetime, timezone, timedelta
from typing import Any

from bson import ObjectId
from pymongo.database import Database

from app.core.time import utc_now

GT_TZ = timezone(timedelta(hours=-6))  # America/Guatemala — UTC-6, sin horario de verano


def _to_gt(dt: datetime) -> str:
    """Convierte un datetime naive (UTC) a string ISO con offset Guatemala (-06:00)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(GT_TZ).isoformat()


TIPOS_EVENTO = {
    'PRODUCTO_CREADO',
    'PRECIO_ACTUALIZADO',
    'DESCRIPCION_ACTUALIZADA',
    'DISPONIBILIDAD_CAMBIADA',
    'ATRIBUTOS_ACTUALIZADOS',
    'PRODUCTO_DESCONTINUADO',
    'ESTADO_PRODUCTO_CAMBIADO',
}


def registrar_evento(
    db: Database,
    producto_id: str,
    tipo_evento: str,
    datos_anteriores: dict,
    datos_nuevos: dict,
    usuario_id: str | None = None,
) -> str:
    """
    Appends un evento al log. Nunca sobreescribe ni borra eventos existentes.
    Devuelve el _id del evento insertado como string.
    """
    if tipo_evento not in TIPOS_EVENTO:
        raise ValueError(f'Tipo de evento desconocido: {tipo_evento}')

    # Obtener la versión actual (último evento del producto)
    ultimo = db.producto_eventos.find_one(
        {'producto_id': producto_id},
        sort=[('version', -1)]
    )
    siguiente_version = (ultimo['version'] + 1) if ultimo else 1

    evento = {
        'producto_id': producto_id,
        'tipo_evento': tipo_evento,
        'datos_anteriores': datos_anteriores,
        'datos_nuevos': datos_nuevos,
        'usuario_id': usuario_id,
        'timestamp': utc_now(),
        'version': siguiente_version,
    }
    resultado = db.producto_eventos.insert_one(evento)
    return str(resultado.inserted_id)


def reconstruir_estado(db: Database, producto_id: str, fecha: datetime) -> dict[str, Any] | None:
    """
    Replay completo: aplica en orden todos los eventos hasta `fecha` inclusive
    y devuelve el estado del producto en ese momento.

    Devuelve None si el producto no existía en esa fecha (el evento PRODUCTO_CREADO
    es posterior a la fecha solicitada).
    """
    eventos = list(
        db.producto_eventos.find(
            {
                'producto_id': producto_id,
                'timestamp': {'$lte': fecha},
            }
        ).sort('version', 1)
    )

    if not eventos:
        return None

    # El primer evento debe ser PRODUCTO_CREADO
    primer_evento = eventos[0]
    if primer_evento['tipo_evento'] != 'PRODUCTO_CREADO':
        # Caso anómalo: hay eventos pero no el de creación antes de la fecha
        return None

    # Estado inicial = datos_nuevos del evento de creación
    estado: dict[str, Any] = dict(primer_evento['datos_nuevos'])

    # Aplicar cada evento posterior en orden
    for evento in eventos[1:]:
        tipo = evento['tipo_evento']
        nuevos = evento['datos_nuevos']

        if tipo == 'PRECIO_ACTUALIZADO':
            estado['precio'] = nuevos.get('precio', estado.get('precio'))

        elif tipo == 'DESCRIPCION_ACTUALIZADA':
            estado['descripcion'] = nuevos.get('descripcion', estado.get('descripcion'))

        elif tipo == 'DISPONIBILIDAD_CAMBIADA':
            estado['disponible'] = nuevos.get('disponible', estado.get('disponible'))

        elif tipo == 'ATRIBUTOS_ACTUALIZADOS':
            if 'atributos' not in estado:
                estado['atributos'] = {}
            estado['atributos'].update(nuevos.get('atributos', {}))

        elif tipo == 'PRODUCTO_DESCONTINUADO':
            estado['estado'] = 'descontinuado'
            estado['disponible'] = False

        elif tipo == 'ESTADO_PRODUCTO_CAMBIADO':
            estado['estado'] = nuevos.get('estado', estado.get('estado'))

    fecha_utc_aware = fecha.replace(tzinfo=timezone.utc) if fecha.tzinfo is None else fecha
    estado['_reconstruido_al'] = fecha_utc_aware.astimezone(GT_TZ).isoformat()
    estado['_version_aplicada'] = eventos[-1]['version']
    return estado


def obtener_historial(db: Database, producto_id: str) -> list[dict]:
    """
    Devuelve la línea de tiempo completa de eventos de un producto,
    ordenada cronológicamente (más antiguo primero).
    """
    eventos = list(
        db.producto_eventos.find({'producto_id': producto_id})
        .sort('version', 1)
    )
    for e in eventos:
        e['_id'] = str(e['_id'])
        if isinstance(e.get('timestamp'), datetime):
            e['timestamp'] = _to_gt(e['timestamp'])
    return eventos
