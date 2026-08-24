from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, DECIMAL, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_mysql import Base
from app.core.time import utc_now


class PedidoVendedor(Base):
    __tablename__ = 'pedido_vendedores'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey('pedidos.id'))
    vendedor_id: Mapped[int] = mapped_column(ForeignKey('vendedores.id'))
    estado: Mapped[str] = mapped_column(
        Enum(
            'pendiente', 'confirmado', 'preparando', 'enviado',
            'entregado', 'cancelado', 'reembolsado',
        ),
        default='pendiente',
    )
    subtotal: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), default=Decimal('0'))
    costo_envio: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), default=Decimal('0'))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )


class PedidoDireccion(Base):
    __tablename__ = 'pedido_direcciones'

    pedido_id: Mapped[int] = mapped_column(
        ForeignKey('pedidos.id'), primary_key=True
    )
    receptor_nombre: Mapped[str] = mapped_column(String(200))
    receptor_telefono: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pais: Mapped[str] = mapped_column(String(60), default='Guatemala')
    departamento: Mapped[str] = mapped_column(String(60))
    municipio: Mapped[str] = mapped_column(String(60))
    linea1: Mapped[str] = mapped_column(String(200))
    linea2: Mapped[str | None] = mapped_column(String(200), nullable=True)
    codigo_postal: Mapped[str | None] = mapped_column(String(10), nullable=True)
