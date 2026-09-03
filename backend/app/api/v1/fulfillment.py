from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.core.db_mysql import get_db
from app.core.deps import get_current_user
from app.models.usuario import Usuario
from app.services import fulfillment_service as service

router = APIRouter(prefix='/fulfillment/orders', tags=['Envíos parciales'])


class ShipmentLine(BaseModel):
    model_config = ConfigDict(extra='forbid')
    pedido_linea_id: int = Field(gt=0)
    cantidad: int = Field(gt=0, strict=True)


class ShipmentCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    lineas: list[ShipmentLine] = Field(min_length=1, max_length=100)
    referencia: str | None = Field(default=None, max_length=120)


@router.get('/{order_id}')
def detail(order_id: int, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.detail(db, order_id, user)


@router.post('/{order_id}/parts/{part_id}/prepare')
def prepare(order_id: int, part_id: int, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    service.prepare_part(db, order_id, part_id, user)
    return service.detail(db, order_id, user)


@router.post('/{order_id}/parts/{part_id}/shipments', status_code=201)
def ship(order_id: int, part_id: int, payload: ShipmentCreate, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    shipment_id = service.create_shipment(db, order_id, part_id, user,
        [line.model_dump() for line in payload.lineas], payload.referencia)
    return {'envio_id': shipment_id, 'pedido': service.detail(db, order_id, user)}


@router.post('/{order_id}/shipments/{shipment_id}/deliver')
def deliver(order_id: int, shipment_id: int, user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    service.deliver_shipment(db, order_id, shipment_id, user)
    return service.detail(db, order_id, user)
