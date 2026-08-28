from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Enum, ForeignKey, DateTime, SmallInteger, DECIMAL
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db_mysql import Base
from app.core.time import utc_now


# Un usuario puede tener solo un carrito activo; los estados "abandonado" y "convertido" son terminales
class Carrito(Base):
    __tablename__ = 'carritos'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id'))
    estado: Mapped[str] = mapped_column(
        Enum('activo', 'abandonado', 'convertido'), default='activo'
    )
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    usuario: Mapped['Usuario'] = relationship(back_populates='carritos')
    items: Mapped[list['CarritoItem']] = relationship(back_populates='carrito', cascade='all, delete-orphan')


# precio_al_agregar guarda el precio en el momento de añadir; puede diferir del precio actual de la oferta
class CarritoItem(Base):
    __tablename__ = 'carrito_items'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    carrito_id: Mapped[int] = mapped_column(ForeignKey('carritos.id'))
    oferta_id: Mapped[int] = mapped_column(ForeignKey('ofertas.id'))
    producto_ref: Mapped[str | None] = mapped_column(String(24))
    cantidad: Mapped[int] = mapped_column(SmallInteger, default=1)
    precio_al_agregar: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))
    fecha_agregado: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    carrito: Mapped['Carrito'] = relationship(back_populates='items')


from app.models.usuario import Usuario  # noqa: E402
