from decimal import Decimal
from pydantic import BaseModel


class CheckoutItem(BaseModel):
    producto_id: int
    cantidad: int


class CheckoutRequest(BaseModel):
    direccion_id: int
    metodo_pago_id: int
    items: list[CheckoutItem]


class CheckoutResponse(BaseModel):
    pedido_id: int
    total: Decimal
    estado: str
    mensaje: str
