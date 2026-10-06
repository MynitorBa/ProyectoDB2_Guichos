from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_mysql import Base
from app.core.time import utc_now


# Bitácora de la saga del checkout: una fila por transición (reserva, cobro,
# confirmación, compensación...). Sirve de evidencia y para el panel de fallas.
class CheckoutSagaPaso(Base):
    __tablename__ = 'checkout_saga_pasos'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey('pedidos.id', ondelete='CASCADE'))
    paso: Mapped[str] = mapped_column(String(40))
    resultado: Mapped[str] = mapped_column(String(30))
    detalle: Mapped[dict | None] = mapped_column(JSON)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
