from decimal import Decimal
from pydantic import BaseModel


# Una línea del checkout: referencia a la oferta del vendedor y la cantidad deseada
class CheckoutItem(BaseModel):
    oferta_id: int
    cantidad: int


# Payload completo que el frontend envía al endpoint POST /orders para crear el pedido
class CheckoutRequest(BaseModel):
    direccion_id: int
    metodo_pago_id: int
    items: list[CheckoutItem]


class CheckoutResponse(BaseModel):
    pedido_id: int
    total: Decimal
    estado: str
    mensaje: str
