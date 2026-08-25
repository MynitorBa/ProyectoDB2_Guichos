from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, SmallInteger, String
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db_mysql import Base
from app.core.time import utc_now


class ProductoImagen(Base):
    __tablename__ = 'producto_imagenes'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    producto_referencia_id: Mapped[int | None] = mapped_column(
        ForeignKey('producto_referencias.id', ondelete='CASCADE'),
        nullable=True,
    )
    subida_por: Mapped[int | None] = mapped_column(
        ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True
    )
    datos: Mapped[bytes] = mapped_column(LONGBLOB, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), default='image/jpeg')
    orden: Mapped[int] = mapped_column(SmallInteger, default=0)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
