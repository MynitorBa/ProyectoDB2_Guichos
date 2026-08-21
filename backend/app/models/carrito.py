from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Enum, ForeignKey, DateTime, SmallInteger, DECIMAL
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db_mysql import Base


class Carrito(Base):
    __tablename__ = 'carritos'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id'))
    estado: Mapped[str] = mapped_column(
        Enum('activo', 'abandonado', 'convertido'), default='activo'
    )
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    usuario: Mapped['Usuario'] = relationship(back_populates='carritos')
    items: Mapped[list['CarritoItem']] = relationship(back_populates='carrito', cascade='all, delete-orphan')


class CarritoItem(Base):
    __tablename__ = 'carrito_items'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    carrito_id: Mapped[int] = mapped_column(ForeignKey('carritos.id'))
    producto_id: Mapped[int] = mapped_column(ForeignKey('productos.id'))
    producto_ref: Mapped[str | None] = mapped_column(String(24))
    cantidad: Mapped[int] = mapped_column(SmallInteger, default=1)
    precio_al_agregar: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))
    fecha_agregado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    carrito: Mapped['Carrito'] = relationship(back_populates='items')


from app.models.usuario import Usuario  # noqa: E402
