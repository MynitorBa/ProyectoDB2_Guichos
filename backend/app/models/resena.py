from datetime import datetime
from sqlalchemy import ForeignKey, DateTime, Text, SmallInteger, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db_mysql import Base
from app.core.time import utc_now


# Reseña ligada al producto_referencia (no a la oferta); aprobada=False la mantiene pendiente de moderación
class Resena(Base):
    __tablename__ = 'resenas'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id'))
    producto_referencia_id: Mapped[int] = mapped_column(
        ForeignKey('producto_referencias.id')
    )
    calificacion: Mapped[int] = mapped_column(SmallInteger)
    comentario: Mapped[str | None] = mapped_column(Text)
    aprobada: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
