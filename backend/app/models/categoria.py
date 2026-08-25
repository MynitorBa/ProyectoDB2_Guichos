from sqlalchemy import String, ForeignKey, Text, SmallInteger, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db_mysql import Base


class Categoria(Base):
    __tablename__ = 'categorias'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    categoria_padre_id: Mapped[int | None] = mapped_column(ForeignKey('categorias.id'))
    nombre: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    sku_prefix: Mapped[str | None] = mapped_column(String(3), unique=True, nullable=True)
    descripcion: Mapped[str | None] = mapped_column(Text)
    imagen_url: Mapped[str | None] = mapped_column(String(500))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    orden: Mapped[int] = mapped_column(SmallInteger, default=0)

    hijos: Mapped[list['Categoria']] = relationship(
        'Categoria', back_populates='padre', foreign_keys=[categoria_padre_id]
    )
    padre: Mapped['Categoria | None'] = relationship(
        'Categoria', back_populates='hijos', remote_side='Categoria.id'
    )
