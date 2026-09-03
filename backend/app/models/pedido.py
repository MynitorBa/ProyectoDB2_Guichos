from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Enum, ForeignKey, DateTime, Text, DECIMAL, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db_mysql import Base
from app.core.time import utc_now


# Pedido global del cliente; puede contener líneas de varios vendedores agrupadas en PedidoVendedor
class Pedido(Base):
    __tablename__ = 'pedidos'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id'))
    direccion_id: Mapped[int] = mapped_column(ForeignKey('direcciones.id'))
    estado: Mapped[str] = mapped_column(
        Enum('pendiente', 'confirmado', 'preparando', 'enviado_parcial', 'enviado', 'entregado_parcial', 'entregado', 'cancelado', 'reembolsado'),
        default='pendiente'
    )
    subtotal: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))
    impuestos: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal('0'))
    total: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))
    notas: Mapped[str | None] = mapped_column(Text)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    usuario: Mapped['Usuario'] = relationship(back_populates='pedidos')
    lineas: Mapped[list['PedidoLinea']] = relationship(back_populates='pedido', cascade='all, delete-orphan')
    pagos: Mapped[list['Pago']] = relationship(back_populates='pedido')


# Cada línea guarda snapshots de nombre, SKU y precio para preservar el historial aunque el producto cambie
class PedidoLinea(Base):
    __tablename__ = 'pedido_lineas'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey('pedidos.id'))
    pedido_vendedor_id: Mapped[int] = mapped_column(
        ForeignKey('pedido_vendedores.id')
    )
    oferta_id: Mapped[int] = mapped_column(
        ForeignKey('ofertas.id')
    )
    producto_ref: Mapped[str] = mapped_column(String(24))
    sku_snapshot: Mapped[str] = mapped_column(String(50))
    producto_nombre: Mapped[str] = mapped_column(String(200))
    vendedor_nombre_snapshot: Mapped[str] = mapped_column(
        String(150)
    )
    precio_unitario: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))
    cantidad: Mapped[int] = mapped_column(SmallInteger)
    subtotal_linea: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))

    pedido: Mapped['Pedido'] = relationship(back_populates='lineas')


from app.models.usuario import Usuario  # noqa: E402
from app.models.pago import Pago        # noqa: E402
