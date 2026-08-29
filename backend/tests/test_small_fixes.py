"""Regresiones pequeñas rescatadas y endurecidas antes de variantes dinámicas."""

from types import SimpleNamespace

import pytest
from bson import ObjectId
from bson.decimal128 import Decimal128
from fastapi import HTTPException

from app.api.v1.admin import RolesUpdate, update_user_roles
from app.services.catalog_service import _serialize
from app.services.product_history_service import registrar_evento


def test_admin_cannot_remove_every_role_from_a_user():
    with pytest.raises(HTTPException) as error:
        update_user_roles(
            user_id=99,
            payload=RolesUpdate(roles=[]),
            current_user=SimpleNamespace(id=1),
            db=None,
        )
    assert error.value.status_code == 400
    assert 'al menos un rol' in error.value.detail


def test_catalog_serializer_handles_nested_bson_without_global_encoders():
    product_id = ObjectId()
    nested_id = ObjectId()
    result = _serialize({
        '_id': product_id,
        'atributos': {'referencia': nested_id, 'precio_lista': Decimal128('12.50')},
        'imagenes': [{'url': '/image/1'}, {'alt': 'sin URL'}, '/legacy.jpg'],
    })

    assert result['_id'] == str(product_id)
    assert result['atributos'] == {
        'referencia': str(nested_id),
        'precio_lista': 12.5,
    }
    assert result['imagenes'] == ['/image/1', '/legacy.jpg']


def test_product_history_accepts_a_legacy_event_without_version():
    class Events:
        def __init__(self):
            self.inserted = None

        def find_one(self, *args, **kwargs):
            return {'producto_id': 'legacy'}

        def insert_one(self, document):
            self.inserted = document
            return SimpleNamespace(inserted_id=ObjectId())

    events = Events()
    database = SimpleNamespace(producto_eventos=events)
    registrar_evento(
        database,
        producto_id='legacy',
        tipo_evento='ATRIBUTOS_ACTUALIZADOS',
        datos_anteriores={},
        datos_nuevos={'nombre': 'Actualizado'},
        usuario_id='1',
    )

    assert events.inserted['version'] == 1
