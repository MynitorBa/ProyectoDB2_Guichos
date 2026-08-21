from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Enum, ForeignKey, DateTime, DECIMAL
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db_mysql import Base


class MetodoPago(Base):
    __tablename__ = 'metodos_pago'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(60), unique=True)
    activo: Mapped[bool] = mapped_column(default=True)


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
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    pedido: Mapped['Pedido'] = relationship(back_populates='pagos')
    metodo: Mapped['MetodoPago'] = relationship()


from app.models.pedido import Pedido  # noqa: E402
