from datetime import datetime
from sqlalchemy import String, Text, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_mysql import Base
from app.core.time import utc_now


# Notificaciones en tiempo real para el usuario; pedido_id permite enlazar directamente al pedido relacionado
class Notificacion(Base):
    __tablename__ = 'notificaciones'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id'))
    tipo: Mapped[str] = mapped_column(String(50))
    titulo: Mapped[str] = mapped_column(String(200))
    mensaje: Mapped[str] = mapped_column(Text)
    leida: Mapped[bool] = mapped_column(Boolean, default=False)
    pedido_id: Mapped[int | None] = mapped_column(ForeignKey('pedidos.id'), nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
