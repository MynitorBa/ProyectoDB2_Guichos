from datetime import datetime
from sqlalchemy import String, Enum, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db_mysql import Base


class Vendedor(Base):
    __tablename__ = 'vendedores'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id'), unique=True)
    nombre_comercial: Mapped[str] = mapped_column(String(150))
    nit: Mapped[str] = mapped_column(String(20), unique=True)
    descripcion: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(String(500))
    estado_verificacion: Mapped[str] = mapped_column(
        Enum('pendiente', 'verificado', 'rechazado'), default='pendiente'
    )
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    productos: Mapped[list['Producto']] = relationship(back_populates='vendedor')


from app.models.producto import Producto  # noqa: E402
