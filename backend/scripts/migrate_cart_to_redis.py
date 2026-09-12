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
from app.models.oferta import Oferta


def main(dry_run: bool = False) -> None:
    engine = create_engine(settings.mysql_url)
    r = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)

    with Session(engine) as db:
        reparados = 0
        # Corrige claves creadas por versiones anteriores que guardaron
        # producto_ref=null aun cuando la oferta sí tenía la referencia.
        for redis_key in r.scan_iter(match='carrito:*'):
            for campo, valor in r.hgetall(redis_key).items():
                try:
                    datos = json.loads(valor)
                    oferta_id = int(campo)
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if datos.get('producto_ref'):
                    continue
                oferta = db.get(Oferta, oferta_id)
                if oferta and oferta.producto_ref:
                    print(f"  Reparar {redis_key}, oferta_id={oferta_id}: producto_ref={oferta.producto_ref}")
                    if not dry_run:
                        datos['producto_ref'] = oferta.producto_ref
                        r.hset(redis_key, campo, json.dumps(datos))
                    reparados += 1

        carritos = db.query(Carrito).filter_by(estado='activo').all()
        print(f"Carritos activos encontrados en MySQL: {len(carritos)}")

        migrados = 0
        for carrito in carritos:
            items = db.query(CarritoItem).filter_by(carrito_id=carrito.id).all()
            if not items:
                print(f"  Carrito #{carrito.id} (usuario {carrito.usuario_id}): vacío -> abandonado.")
                if not dry_run:
                    carrito.estado = 'abandonado'
                continue

            redis_key = f"carrito:{carrito.usuario_id}"
            print(f"  Carrito #{carrito.id} (usuario {carrito.usuario_id}): {len(items)} item(s) -> {redis_key}")

            if not dry_run:
                for item in items:
                    oferta = db.get(Oferta, item.oferta_id)
                    producto_ref = item.producto_ref or (oferta.producto_ref if oferta else None)
                    campo = str(item.oferta_id)
                    valor = json.dumps({
                        "cantidad": item.cantidad,
                        "precio_al_agregar": str(item.precio_al_agregar),
                        "producto_ref": producto_ref,
                    })
                    r.hset(redis_key, campo, valor)
                    print(f"    oferta_id={item.oferta_id}  cantidad={item.cantidad}  precio={item.precio_al_agregar}")

                r.expire(redis_key, settings.REDIS_CART_TTL)
                carrito.estado = 'abandonado'
                migrados += 1

        if not dry_run:
            db.commit()
            print(
                f"\nMigración completa: {migrados} carrito(s) movidos, "
                f"{reparados} referencia(s) Redis reparadas y todos los carritos "
                "SQL procesados quedaron abandonados."
            )
        else:
            print(
                f"\n[DRY-RUN] Se migrarían {len([c for c in carritos if c.items])} "
                f"carrito(s) y se repararían {reparados} referencia(s). Nada fue escrito."
            )


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Solo muestra, no escribe nada.')
    args = parser.parse_args()
    main(dry_run=args.dry_run)
