#!/usr/bin/env python3
"""Prueba reversible de creación y lectura pública de una variante."""

import json
import os
import sys
import urllib.request
from uuid import uuid4

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bson import ObjectId

from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import SessionLocal
from app.models.producto_variante_referencia import ProductoVarianteReferencia


BASE_URL = os.getenv('API_URL', 'http://127.0.0.1:8000/api/v1')


def request(method, path, payload=None, token=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(
        f'{BASE_URL}{path}', data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read())


def main():
    created = None
    db = SessionLocal()
    mongo = get_mongo_db()
    try:
        login = request('POST', '/auth/login', {
            'email': 'admin@tiendaya.gt', 'password': 'password123',
        })
        catalog = request('GET', '/products?page_size=1&orden=nombre_asc')
        product = catalog['items'][0]
        marker = f'prueba_{uuid4().hex[:8]}'
        created = request(
            'POST',
            f'/admin/products/{product["_id"]}/variants',
            {'atributos': {'validacion_temporal': marker}},
            login['access_token'],
        )
        detail = request('GET', f'/products/{product["_id"]}')
        found = next(
            (item for item in detail['variantes']
             if item['variante_id'] == created['variante_id']),
            None,
        )
        if not found or found['atributos'].get('validacion_temporal') != marker:
            raise RuntimeError('La variante creada no apareció en el detalle público.')
        print(
            f'OK: variante dinámica #{created["variante_id"]} creada y leída '
            f'en {product["nombre"]}.'
        )
        return 0
    finally:
        if created:
            row = db.get(ProductoVarianteReferencia, created['variante_id'])
            if row:
                mongo.producto_variantes.delete_one({'_id': ObjectId(row.variante_ref)})
                db.delete(row)
                db.commit()
        db.close()


if __name__ == '__main__':
    raise SystemExit(main())
