from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_mysql import Base
from app.core.time import utc_now


# Ancla SQL del producto; el detalle completo vive en MongoDB (producto_ref como clave compartida)
class ProductoReferencia(Base):
    """Identidad SQL mínima para relaciones que pertenecen al producto."""

    __tablename__ = 'producto_referencias'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    producto_ref: Mapped[str] = mapped_column(String(24), unique=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey('categorias.id'))
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now
    )
