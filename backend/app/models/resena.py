from datetime import datetime
from sqlalchemy import ForeignKey, DateTime, Text, SmallInteger, Boolean, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db_mysql import Base
from app.core.time import utc_now


# Reseña ligada al producto_referencia (no a la oferta); aprobada=False la mantiene pendiente de moderación
class Resena(Base):
    __tablename__ = 'resenas'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), unique=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id'))
    producto_referencia_id: Mapped[int] = mapped_column(
        ForeignKey('producto_referencias.id')
    )
    vendedor_id: Mapped[int | None] = mapped_column(
        ForeignKey('vendedores.id'), nullable=True
    )
    pedido_linea_id: Mapped[int | None] = mapped_column(
        ForeignKey('pedido_lineas.id'), nullable=True
    )
    calificacion: Mapped[int] = mapped_column(SmallInteger)
    comentario: Mapped[str | None] = mapped_column(Text)
    estado_moderacion: Mapped[str] = mapped_column(
        Enum('pendiente', 'aprobada', 'rechazada'), default='pendiente'
    )
    verificada_compra: Mapped[bool] = mapped_column(Boolean, default=False)
    motivo_no_verificada: Mapped[str | None] = mapped_column(String(160), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    # Compatibilidad temporal con consultas y migraciones anteriores.
    aprobada: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )


class ResenaImagen(Base):
    __tablename__ = 'resena_imagenes'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    resena_id: Mapped[int] = mapped_column(ForeignKey('resenas.id'))
    url: Mapped[str] = mapped_column(String(500))
    orden: Mapped[int] = mapped_column(SmallInteger, default=0)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ResenaRespuesta(Base):
    __tablename__ = 'resena_respuestas'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), unique=True)
    resena_id: Mapped[int] = mapped_column(ForeignKey('resenas.id'))
    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id'))
    vendedor_id: Mapped[int] = mapped_column(ForeignKey('vendedores.id'))
    texto: Mapped[str] = mapped_column(Text)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
