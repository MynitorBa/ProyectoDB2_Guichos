from datetime import datetime
from sqlalchemy import String, Enum, ForeignKey, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db_mysql import Base


class Inventario(Base):
    __tablename__ = 'inventario'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey('productos.id'))
    cantidad_disponible: Mapped[int] = mapped_column(Integer, default=0)
    cantidad_reservada: Mapped[int] = mapped_column(Integer, default=0)
    punto_reorden: Mapped[int] = mapped_column(Integer, default=5)
    bodega: Mapped[str] = mapped_column(String(60), default='principal')
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    producto: Mapped['Producto'] = relationship(back_populates='inventario')


class MovimientoInventario(Base):
    __tablename__ = 'movimientos_inventario'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey('productos.id'))
    tipo: Mapped[str] = mapped_column(
        Enum('entrada', 'salida', 'ajuste', 'reserva', 'liberacion')
    )
    cantidad: Mapped[int] = mapped_column(Integer)
    motivo: Mapped[str] = mapped_column(String(100))
    pedido_id: Mapped[int | None] = mapped_column(ForeignKey('pedidos.id'), nullable=True)
    usuario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


from app.models.producto import Producto  # noqa: E402
