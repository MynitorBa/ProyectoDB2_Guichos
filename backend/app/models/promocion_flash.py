from datetime import datetime
from decimal import Decimal

from sqlalchemy import Computed, DateTime, DECIMAL, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_mysql import Base
from app.core.time import utc_now


class PromocionFlash(Base):
    __tablename__ = 'promociones_flash'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    oferta_id: Mapped[int] = mapped_column(ForeignKey('ofertas.id'))
    creado_por: Mapped[int] = mapped_column(ForeignKey('usuarios.id'))
    precio_promocional: Mapped[Decimal] = mapped_column(DECIMAL(12, 2))
    unidades_totales: Mapped[int] = mapped_column(Integer)
    unidades_vendidas: Mapped[int] = mapped_column(Integer, default=0)
    max_por_usuario: Mapped[int] = mapped_column(Integer, default=1)
    segundos_reserva: Mapped[int] = mapped_column(Integer, default=300)
    inicia_en: Mapped[datetime] = mapped_column(DateTime)
    finaliza_en: Mapped[datetime] = mapped_column(DateTime)
    estado: Mapped[str] = mapped_column(
        Enum('programada', 'activa', 'finalizada', 'cancelada'), default='programada'
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )
    slot_vigente: Mapped[int | None] = mapped_column(
        Integer, Computed("IF(estado IN ('programada','activa'), 1, NULL)", persisted=True)
    )


class ReservaFlash(Base):
    __tablename__ = 'reservas_flash'

    token: Mapped[str] = mapped_column(primary_key=True)
    promocion_id: Mapped[int] = mapped_column(ForeignKey('promociones_flash.id'))
    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id'))
    cantidad: Mapped[int] = mapped_column(Integer)
    precio_unitario: Mapped[Decimal] = mapped_column(DECIMAL(12, 2))
    estado: Mapped[str] = mapped_column(
        Enum('reservada', 'convertida', 'expirada', 'cancelada'), default='reservada'
    )
    expira_en: Mapped[datetime] = mapped_column(DateTime)
    pedido_id: Mapped[int | None] = mapped_column(ForeignKey('pedidos.id'), nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )
    slot_activo: Mapped[int | None] = mapped_column(
        Integer, Computed("IF(estado='reservada', 1, NULL)", persisted=True)
    )
