from decimal import Decimal
from pydantic import BaseModel, Field


# Una línea del checkout: referencia a la oferta del vendedor y la cantidad deseada
class CheckoutItem(BaseModel):
    oferta_id: int
    cantidad: int


# Payload completo que el frontend envía al endpoint POST /orders para crear el pedido
class CheckoutRequest(BaseModel):
    direccion_id: int
    metodo_pago_id: int
    # Se conserva temporalmente para no romper clientes anteriores, pero el
    # backend reconstruye las líneas desde el carrito Redis autenticado.
    items: list[CheckoutItem] = Field(default_factory=list)
    confirmar_cambios_precio: bool = False
    precios_confirmados: dict[int, Decimal] = Field(default_factory=dict)


class CheckoutResponse(BaseModel):
    pedido_id: int
    total: Decimal
    estado: str
    mensaje: str
