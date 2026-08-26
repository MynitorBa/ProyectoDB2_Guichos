"""Respalda y limpia eventos MongoDB que no pertenecen al producto documental."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

from bson import json_util

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.db_mongo import get_mongo_db
from app.services.product_history_service import reconstruir_estado, registrar_evento


OPERATIONAL_TYPES = {'PRECIO_ACTUALIZADO', 'DISPONIBILIDAD_CAMBIADA'}


def main(*, apply: bool) -> int:
    mongo = get_mongo_db()
    products = list(mongo.productos.find({}, {'_id': 1}))
    remove_ids = []
    affected_products = set()

    for product in products:
        product_id = str(product['_id'])
        events = list(mongo.producto_eventos.find({'producto_id': product_id}))
        created = next((
            event.get('timestamp') for event in events
            if event.get('tipo_evento') == 'PRODUCTO_CREADO'
        ), None)
        for event in events:
            is_operational = event.get('tipo_evento') in OPERATIONAL_TYPES
            is_before_creation = bool(
                created and event.get('timestamp') and event['timestamp'] < created
            )
            if is_operational or is_before_creation:
                remove_ids.append(event['_id'])
                affected_products.add(product_id)

    state_mismatches = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for product in mongo.productos.find({}, {'_id': 1, 'estado': 1}):
        product_id = str(product['_id'])
        replay = reconstruir_estado(mongo, product_id, now)
        replay_state = replay.get('estado') if replay else None
        current_state = product.get('estado', 'activo')
        if replay_state != current_state:
            state_mismatches.append((product_id, replay_state, current_state))

    print(f'Eventos a retirar de MongoDB: {len(remove_ids)}')
    print(f'Productos afectados: {len(affected_products)}')
    print(f'Estados documentales a reconciliar: {len(state_mismatches)}')
    if not apply:
        print('Modo diagnóstico; no se modificaron datos.')
        return 0
    if not remove_ids and not state_mismatches:
        print('No había datos que reparar.')
        return 0

    backup_dir = ROOT.parent / 'backups' / 'history_cleanup'
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    backup_path = backup_dir / f'producto_eventos_{stamp}.json'
    all_events = list(mongo.producto_eventos.find({}))
    backup_path.write_text(json_util.dumps(all_events, indent=2), encoding='utf-8')

    result = mongo.producto_eventos.delete_many({'_id': {'$in': remove_ids}})
    for product_id in affected_products:
        remaining = list(mongo.producto_eventos.find(
            {'producto_id': product_id}
        ).sort([('timestamp', 1), ('_id', 1)]))
        for version, event in enumerate(remaining, start=1):
            mongo.producto_eventos.update_one(
                {'_id': event['_id']}, {'$set': {'version': version}}
            )

    reconciled = 0
    for product in mongo.productos.find({}, {'_id': 1, 'estado': 1}):
        product_id = str(product['_id'])
        replay = reconstruir_estado(mongo, product_id, now)
        replay_state = replay.get('estado') if replay else None
        current_state = product.get('estado', 'activo')
        if replay_state != current_state:
            registrar_evento(
                mongo,
                producto_id=product_id,
                tipo_evento='ESTADO_PRODUCTO_CAMBIADO',
                datos_anteriores={'estado': replay_state},
                datos_nuevos={
                    'estado': current_state,
                    'motivo': 'Reconciliación del estado documental existente',
                },
                usuario_id=None,
            )
            reconciled += 1

    print(f'Eventos retirados: {result.deleted_count}')
    print(f'Estados reconciliados: {reconciled}')
    print(f'Respaldo recuperable: {backup_path}')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    raise SystemExit(main(apply=args.apply))
