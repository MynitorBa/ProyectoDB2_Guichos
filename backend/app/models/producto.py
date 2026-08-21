from datetime import datetime
from sqlalchemy import String, Enum, ForeignKey, DateTime, Text, DECIMAL, Boolean, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from decimal import Decimal

from app.core.db_mysql import Base


class Producto(Base):
    __tablename__ = 'productos'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str | None] = mapped_column(Text)
    precio: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))
    categoria_id: Mapped[int] = mapped_column(ForeignKey('categorias.id'))
    vendedor_id: Mapped[int] = mapped_column(ForeignKey('vendedores.id'))
    producto_ref: Mapped[str | None] = mapped_column(String(24))
    estado: Mapped[str] = mapped_column(
        Enum('activo', 'inactivo', 'borrador', 'descontinuado'), default='activo'
    )
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    categoria: Mapped['Categoria'] = relationship(back_populates='productos')
    vendedor: Mapped['Vendedor'] = relationship(back_populates='productos')
    imagenes: Mapped[list['ProductoImagen']] = relationship(back_populates='producto', cascade='all, delete-orphan')
    inventario: Mapped[list['Inventario']] = relationship(back_populates='producto')


class ProductoImagen(Base):
    __tablename__ = 'producto_imagenes'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey('productos.id'))
    url: Mapped[str] = mapped_column(String(500))
    alt_text: Mapped[str | None] = mapped_column(String(200))
    orden: Mapped[int] = mapped_column(SmallInteger, default=0)
    es_principal: Mapped[bool] = mapped_column(Boolean, default=False)

    producto: Mapped['Producto'] = relationship(back_populates='imagenes')


from app.models.categoria import Categoria  # noqa: E402
from app.models.vendedor import Vendedor    # noqa: E402
from app.models.inventario import Inventario  # noqa: E402
