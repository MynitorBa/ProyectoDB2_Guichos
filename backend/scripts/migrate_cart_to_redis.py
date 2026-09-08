"""
Migración de carritos activos de MySQL → Redis.

Qué hace:
  1. Lee todos los carritos con estado='activo' en MySQL.
  2. Por cada uno, escribe sus ítems como HASH en Redis (misma estructura que redis_cart_service).
  3. Marca el carrito MySQL como 'abandonado' para que no vuelva a procesarse.
     (Las tablas permanecen como registro histórico, no se borran.)

Uso:
  python scripts/migrate_cart_to_redis.py
  python scripts/migrate_cart_to_redis.py --dry-run   ← solo muestra, no escribe
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import redis
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.carrito import Carrito, CarritoItem  # noqa: modelos SQL


def main(dry_run: bool = False) -> None:
    engine = create_engine(settings.mysql_url)
    r = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)

    with Session(engine) as db:
        carritos = db.query(Carrito).filter_by(estado='activo').all()
        print(f"Carritos activos encontrados en MySQL: {len(carritos)}")

        migrados = 0
        for carrito in carritos:
            items = db.query(CarritoItem).filter_by(carrito_id=carrito.id).all()
            if not items:
                print(f"  Carrito #{carrito.id} (usuario {carrito.usuario_id}): vacío, se omite.")
                continue

            redis_key = f"carrito:{carrito.usuario_id}"
            print(f"  Carrito #{carrito.id} (usuario {carrito.usuario_id}): {len(items)} item(s) -> {redis_key}")

            if not dry_run:
                for item in items:
                    campo = str(item.oferta_id)
                    valor = json.dumps({
                        "cantidad": item.cantidad,
                        "precio_al_agregar": str(item.precio_al_agregar),
                        "producto_ref": item.producto_ref,
                    })
                    r.hset(redis_key, campo, valor)
                    print(f"    oferta_id={item.oferta_id}  cantidad={item.cantidad}  precio={item.precio_al_agregar}")

                r.expire(redis_key, settings.REDIS_CART_TTL)
                carrito.estado = 'abandonado'
                migrados += 1

        if not dry_run:
            db.commit()
            print(f"\nMigración completa: {migrados} carrito(s) movidos a Redis, marcados como 'abandonado' en MySQL.")
        else:
            print(f"\n[DRY-RUN] Se migrarían {len([c for c in carritos if c.items])} carrito(s). Nada fue escrito.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Solo muestra, no escribe nada.')
    args = parser.parse_args()
    main(dry_run=args.dry_run)
