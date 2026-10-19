from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_mysql import Base
from app.core.time import utc_now


class AlertaFraude(Base):
    __tablename__ = 'alertas_fraude'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    huella: Mapped[str] = mapped_column(String(64), unique=True)
    tipo: Mapped[str] = mapped_column(String(60))
    prioridad: Mapped[str] = mapped_column(
        Enum('informativa', 'baja', 'media', 'alta'), default='baja'
    )
    estado: Mapped[str] = mapped_column(
        Enum('pendiente', 'en_revision', 'descartada', 'revisada'), default='pendiente'
    )
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey('usuarios.id'))
    vendedor_id: Mapped[int | None] = mapped_column(ForeignKey('vendedores.id'))
    producto_ref: Mapped[str | None] = mapped_column(String(24))
    oferta_id: Mapped[int | None] = mapped_column(ForeignKey('ofertas.id'))
    motivos: Mapped[list] = mapped_column(JSON)
    evidencias: Mapped[dict] = mapped_column(JSON)
    primera_deteccion: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    ultima_deteccion: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    resuelta_en: Mapped[datetime | None] = mapped_column(DateTime)
    ultima_ejecucion_id: Mapped[int | None] = mapped_column(
        ForeignKey('fraud_analysis_runs.id')
    )
    origen_ultima_deteccion: Mapped[str | None] = mapped_column(
        Enum('manual', 'automatico')
    )
    revisada_por: Mapped[int | None] = mapped_column(ForeignKey('usuarios.id'))
    notas_revision: Mapped[str | None] = mapped_column(Text)
