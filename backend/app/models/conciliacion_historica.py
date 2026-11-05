from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_mysql import Base
from app.core.time import utc_now


class ConciliacionHistorica(Base):
    """Auditoría y candado idempotente de una corrección histórica autorizada."""

    __tablename__ = 'conciliaciones_historicas'
    __table_args__ = (
        UniqueConstraint('entorno', 'pedido_id', 'tipo_conciliacion',
                         name='uq_conciliacion_entorno_pedido_tipo'),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    operacion_id: Mapped[str] = mapped_column(String(36), unique=True)
    entorno: Mapped[str] = mapped_column(String(40))
    pedido_id: Mapped[int] = mapped_column(ForeignKey('pedidos.id'))
    pago_id: Mapped[int] = mapped_column(ForeignKey('pagos.id'))
    tipo_conciliacion: Mapped[str] = mapped_column(String(80))
    huella: Mapped[str] = mapped_column(String(64), unique=True)
    referencia_cobro: Mapped[str] = mapped_column(String(100))
    responsable_usuario_id: Mapped[int | None] = mapped_column(ForeignKey('usuarios.id'))
    estado: Mapped[str] = mapped_column(Enum('aplicada', 'revertida'))
    resultado: Mapped[str] = mapped_column(String(120))
    datos_auditoria: Mapped[dict] = mapped_column(JSON)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
