from datetime import datetime
from sqlalchemy import String, Enum, ForeignKey, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db_mysql import Base
from app.core.time import utc_now


class Inventario(Base):
    __tablename__ = 'inventario'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    oferta_id: Mapped[int] = mapped_column(ForeignKey('ofertas.id'))
    cantidad_disponible: Mapped[int] = mapped_column(Integer, default=0)
    cantidad_reservada: Mapped[int] = mapped_column(Integer, default=0)
    punto_reorden: Mapped[int] = mapped_column(Integer, default=5)
    bodega: Mapped[str] = mapped_column(String(60), default='principal')
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

class MovimientoInventario(Base):
    __tablename__ = 'movimientos_inventario'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    inventario_id: Mapped[int] = mapped_column(ForeignKey('inventario.id'))
    tipo: Mapped[str] = mapped_column(
        Enum('entrada', 'salida', 'ajuste', 'reserva', 'liberacion')
    )
    cantidad: Mapped[int] = mapped_column(Integer)
    motivo: Mapped[str] = mapped_column(String(100))
    pedido_id: Mapped[int | None] = mapped_column(ForeignKey('pedidos.id'), nullable=True)
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey('usuarios.id'), nullable=True
    )
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
