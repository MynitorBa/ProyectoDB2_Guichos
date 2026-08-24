from datetime import datetime

from sqlalchemy import DateTime, Enum, JSON, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_mysql import Base
from app.core.time import utc_now


class OutboxEvento(Base):
    __tablename__ = 'outbox_eventos'

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tipo_evento: Mapped[str] = mapped_column(String(100))
    agregado_tipo: Mapped[str] = mapped_column(String(60))
    agregado_id: Mapped[str] = mapped_column(String(64))
    producto_ref: Mapped[str | None] = mapped_column(String(24), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    estado: Mapped[str] = mapped_column(
        Enum('pendiente', 'procesando', 'procesado', 'error'),
        default='pendiente',
    )
    intentos: Mapped[int] = mapped_column(SmallInteger, default=0)
    ultimo_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    procesado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
