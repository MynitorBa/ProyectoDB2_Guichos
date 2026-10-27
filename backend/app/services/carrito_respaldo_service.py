"""Copia del carrito en MySQL: el plan B cuando Redis no responde.

Redis sigue siendo el camino rápido. Cada escritura exitosa en Redis se copia
aquí (``espejar``); si Redis no responde, ``redis_cart_service`` usa estas
tablas para leer y escribir y marca ``pendiente_redis = 1``. Cuando Redis
vuelve, el carrito se reconstruye desde aquí antes de la siguiente operación.

Cada ítem guarda el mismo JSON que el campo del HASH ``carrito:{usuario}``,
así el paso de un almacén al otro no traduce nada.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Callable

from sqlalchemy import bindparam, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db_mysql import SessionLocal
from app.core.time import utc_now

TTL = settings.REDIS_CART_TTL
_BLOQUEO = {1205, 1213}  # lock wait timeout, deadlock


def _items(db: Session, usuario_id: int) -> dict[int, str]:
    filas = db.execute(text(
        'SELECT oferta_id, datos FROM carritos_respaldo_items WHERE usuario_id = :u'
    ), {'u': usuario_id}).all()
    return {int(oferta_id): datos if isinstance(datos, str) else json.dumps(datos) for oferta_id, datos in filas}


def _guardar(db: Session, usuario_id: int, items: dict[int, str], *, pendiente: bool,
             ttl: int | None = None) -> None:
    ahora = utc_now()
    expira = ahora + timedelta(seconds=ttl if ttl and ttl > 0 else TTL)
    db.execute(text("""
        INSERT INTO carritos_respaldo (usuario_id, pendiente_redis, expira_en, actualizado_en)
        VALUES (:u, :p, :e, :a)
        ON DUPLICATE KEY UPDATE pendiente_redis = :p, expira_en = :e, actualizado_en = :a
    """), {'u': usuario_id, 'p': int(pendiente), 'e': expira, 'a': ahora})
    db.execute(text('DELETE FROM carritos_respaldo_items WHERE usuario_id = :u'), {'u': usuario_id})
    for oferta_id, datos in items.items():
        db.execute(text(
            'INSERT INTO carritos_respaldo_items (usuario_id, oferta_id, datos) VALUES (:u, :o, :d)'
        ), {'u': usuario_id, 'o': oferta_id, 'd': datos})


def _vigente(db: Session, usuario_id: int, *, bloquear: bool = False) -> dict | None:
    """Fila del carrito si existe y no expiró; un carrito vencido se borra."""
    sql = 'SELECT pendiente_redis, expira_en FROM carritos_respaldo WHERE usuario_id = :u'
    fila = db.execute(text(sql + (' FOR UPDATE' if bloquear else '')), {'u': usuario_id}).first()
    if not fila:
        return None
    if fila.expira_en <= utc_now():
        db.execute(text('DELETE FROM carritos_respaldo WHERE usuario_id = :u'), {'u': usuario_id})
        return None
    return {'pendiente': bool(fila.pendiente_redis), 'expira_en': fila.expira_en}


def _bloquear(db: Session, usuario_id: int) -> None:
    """Crea la fila del carrito si falta y la deja bloqueada para esta transacción.

    ``ON DUPLICATE KEY UPDATE`` toma el candado exclusivo desde el inicio; un
    ``INSERT IGNORE`` seguido de ``FOR UPDATE`` tomaría primero uno compartido
    y dos solicitudes simultáneas se bloquearían entre sí (deadlock).
    """
    db.execute(text("""
        INSERT INTO carritos_respaldo (usuario_id, pendiente_redis, expira_en, actualizado_en)
        VALUES (:u, 0, :e, :a)
        ON DUPLICATE KEY UPDATE usuario_id = usuario_id
    """), {'u': usuario_id, 'e': utc_now() + timedelta(seconds=TTL), 'a': utc_now()})


def _con_reintento(operacion: Callable[[], object]):
    """Repite la transacción si MySQL la eligió como víctima de un deadlock."""
    for intento in range(3):
        try:
            return operacion()
        except OperationalError as exc:
            codigo = exc.orig.args[0] if getattr(exc, 'orig', None) is not None and exc.orig.args else None
            if codigo not in _BLOQUEO or intento == 2:
                raise


# ── Operaciones del respaldo (cuando Redis no responde) ──────────────────────

def leer(usuario_id: int) -> dict[int, str]:
    """Ítems vigentes (JSON crudo por oferta) y renueva la expiración, como Redis."""
    with SessionLocal() as db:
        estado = _vigente(db, usuario_id, bloquear=True)
        if not estado:
            db.commit()
            return {}
        db.execute(text(
            'UPDATE carritos_respaldo SET expira_en = :e WHERE usuario_id = :u'
        ), {'u': usuario_id, 'e': utc_now() + timedelta(seconds=TTL)})
        items = _items(db, usuario_id)
        db.commit()
        return items


def modificar(usuario_id: int, cambio: Callable[[dict[int, str]], object]):
    """Aplica ``cambio`` sobre los ítems con la fila bloqueada y marca el carrito pendiente.

    El bloqueo de la fila del carrito serializa dos solicitudes simultáneas del
    mismo usuario, igual que el script Lua lo hace en Redis.
    """
    def transaccion():
        with SessionLocal() as db:
            _bloquear(db, usuario_id)
            estado = _vigente(db, usuario_id, bloquear=True)
            items = _items(db, usuario_id) if estado else {}
            resultado = cambio(items)
            _guardar(db, usuario_id, items, pendiente=True)
            db.commit()
            return resultado

    return _con_reintento(transaccion)


def segundos_restantes(usuario_id: int) -> int:
    """Como ``TTL`` de Redis: -2 si no hay carrito."""
    with SessionLocal() as db:
        estado = _vigente(db, usuario_id)
        db.commit()
    if not estado:
        return -2
    return max(0, int((estado['expira_en'] - utc_now()).total_seconds()))


def vaciar(usuario_id: int, *, pendiente: bool) -> None:
    with SessionLocal() as db:
        _guardar(db, usuario_id, {}, pendiente=pendiente)
        db.commit()


# ── Sincronización con Redis ──────────────────────────────────────────────────

def espejar(usuario_id: int, leer_redis: Callable[[], tuple[dict[int, str], int]]) -> None:
    """Copia el estado que acaba de quedar en Redis (no pendiente).

    Redis se lee **con la fila del carrito bloqueada**: si dos solicitudes del
    mismo usuario copian a la vez, la segunda espera y lee el estado más nuevo,
    así una foto vieja nunca pisa a una reciente.
    """
    def transaccion():
        with SessionLocal() as db:
            _bloquear(db, usuario_id)
            items, ttl = leer_redis()
            _guardar(db, usuario_id, items, pendiente=False, ttl=ttl)
            db.commit()

    _con_reintento(transaccion)


def pendiente(usuario_id: int) -> dict | None:
    """Si el carrito cambió solo en MySQL: sus ítems y segundos restantes; si no, None."""
    with SessionLocal() as db:
        estado = _vigente(db, usuario_id)
        if estado is None:
            # Un carrito vencido o inexistente que estaba pendiente ya se borró:
            # Redis tampoco debe conservar nada de él.
            fila = None
        elif estado['pendiente']:
            fila = {
                'items': _items(db, usuario_id),
                'ttl': max(1, int((estado['expira_en'] - utc_now()).total_seconds())),
            }
        else:
            fila = None
        db.commit()
        return fila


def marcar_sincronizado(usuario_id: int) -> None:
    with SessionLocal() as db:
        db.execute(text(
            'UPDATE carritos_respaldo SET pendiente_redis = 0 WHERE usuario_id = :u'
        ), {'u': usuario_id})
        db.commit()


def quitar_ofertas(db: Session, usuario_id: int, oferta_ids: list[int]) -> None:
    """Retira lo comprado dentro de la transacción que confirma el pedido."""
    if not oferta_ids:
        return
    db.execute(text(
        'DELETE FROM carritos_respaldo_items WHERE usuario_id = :u AND oferta_id IN :ids'
    ).bindparams(bindparam('ids', expanding=True)),
        {'u': usuario_id, 'ids': list(oferta_ids)})
