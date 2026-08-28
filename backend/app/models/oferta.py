from datetime import datetime
from decimal import Decimal

from sqlalchemy import Computed, DateTime, DECIMAL, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_mysql import Base
from app.core.time import utc_now


# Vínculo vendedor-producto con precio; un mismo producto_ref puede tener ofertas de distintos vendedores
class Oferta(Base):
    __tablename__ = 'ofertas'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    producto_ref: Mapped[str] = mapped_column(
        ForeignKey('producto_referencias.producto_ref')
    )
    vendedor_id: Mapped[int] = mapped_column(ForeignKey('vendedores.id'))
    sku: Mapped[str] = mapped_column(String(50))
    precio_actual: Mapped[Decimal] = mapped_column(DECIMAL(12, 2))
    moneda: Mapped[str] = mapped_column(String(3), default='GTQ')
    estado: Mapped[str] = mapped_column(
        Enum('borrador', 'activa', 'pausada', 'descontinuada'),
        default='activa',
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )


# Historial SCD tipo 2 de precios; es_vigente identifica el precio actualmente en vigor
class OfertaPrecioHistorial(Base):
    __tablename__ = 'oferta_precios_historial'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    oferta_id: Mapped[int] = mapped_column(ForeignKey('ofertas.id'))
    precio: Mapped[Decimal] = mapped_column(DECIMAL(12, 2))
    moneda: Mapped[str] = mapped_column(String(3), default='GTQ')
    vigente_desde: Mapped[datetime] = mapped_column(DateTime)
    vigente_hasta: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cambiado_por: Mapped[int | None] = mapped_column(
        ForeignKey('usuarios.id'), nullable=True
    )
    motivo: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    es_vigente: Mapped[int | None] = mapped_column(
        Integer,
        Computed('IF(vigente_hasta IS NULL, 1, NULL)', persisted=True),
        nullable=True,
    )


class OfertaEstadoHistorial(Base):
    """Intervalos de vigencia de la configuración comercial de una oferta."""

    __tablename__ = 'oferta_estados_historial'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    oferta_id: Mapped[int] = mapped_column(ForeignKey('ofertas.id'))
    vendedor_id: Mapped[int] = mapped_column(ForeignKey('vendedores.id'))
    sku: Mapped[str] = mapped_column(String(50))
    estado: Mapped[str] = mapped_column(
        Enum('borrador', 'activa', 'pausada', 'descontinuada')
    )
    vigente_desde: Mapped[datetime] = mapped_column(DateTime)
    vigente_hasta: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cambiado_por: Mapped[int | None] = mapped_column(
        ForeignKey('usuarios.id'), nullable=True
    )
    motivo: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    es_vigente: Mapped[int | None] = mapped_column(
        Integer,
        Computed('IF(vigente_hasta IS NULL, 1, NULL)', persisted=True),
        nullable=True,
    )
