from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_mysql import Base
from app.core.time import utc_now


class FraudAnalysisRun(Base):
    __tablename__ = 'fraud_analysis_runs'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    origen: Mapped[str] = mapped_column(Enum('manual', 'automatico'))
    estado: Mapped[str] = mapped_column(
        Enum('en_curso', 'exitosa', 'fallida'), default='en_curso'
    )
    iniciada_en: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    finalizada_en: Mapped[datetime | None] = mapped_column(DateTime)
    duracion_ms: Mapped[int | None] = mapped_column(Integer)
    resumen: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    ejecutor: Mapped[str | None] = mapped_column(String(160))
