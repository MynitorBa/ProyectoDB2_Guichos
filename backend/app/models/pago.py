from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Enum, ForeignKey, DateTime, DECIMAL
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db_mysql import Base
from app.core.time import utc_now


# Catálogo de métodos de pago habilitados (ej: tarjeta, efectivo); se administra desde el panel admin
class MetodoPago(Base):
    __tablename__ = 'metodos_pago'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(60), unique=True)
    activo: Mapped[bool] = mapped_column(default=True)


# Transacción de pago asociada a un pedido; referencia_transaccion almacena el ID del gateway externo
class Pago(Base):
    __tablename__ = 'pagos'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey('pedidos.id'))
    metodo_pago_id: Mapped[int] = mapped_column(ForeignKey('metodos_pago.id'))
    monto: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))
    estado: Mapped[str] = mapped_column(
        Enum('pendiente', 'aprobado', 'rechazado', 'reembolsado'), default='pendiente'
    )
    referencia_transaccion: Mapped[str | None] = mapped_column(String(100))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    pedido: Mapped['Pedido'] = relationship(back_populates='pagos')
    metodo: Mapped['MetodoPago'] = relationship()


from app.models.pedido import Pedido  # noqa: E402
