from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_mysql import Base
from app.core.time import utc_now


class ProductoVarianteReferencia(Base):
    """Ancla SQL mínima de una variante cuyo detalle vive en MongoDB."""

    __tablename__ = 'producto_variante_referencias'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    producto_referencia_id: Mapped[int] = mapped_column(
        ForeignKey('producto_referencias.id')
    )
    variante_ref: Mapped[str] = mapped_column(String(24), unique=True)
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
