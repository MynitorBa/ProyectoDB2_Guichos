from datetime import datetime
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db_mysql import Base
from app.core.time import utc_now


class PedidoEnvio(Base):
    __tablename__ = 'pedido_envios'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pedido_vendedor_id: Mapped[int] = mapped_column(ForeignKey('pedido_vendedores.id'))
    estado: Mapped[str] = mapped_column(Enum('enviado', 'entregado'), default='enviado')
    referencia: Mapped[str | None] = mapped_column(String(120), nullable=True)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey('usuarios.id'), nullable=True)
    entregado_por: Mapped[int | None] = mapped_column(ForeignKey('usuarios.id'), nullable=True)
    fecha_envio: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fecha_entrega: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    legado: Mapped[bool] = mapped_column(Boolean, default=False)


class PedidoEnvioLinea(Base):
    __tablename__ = 'pedido_envio_lineas'
    envio_id: Mapped[int] = mapped_column(ForeignKey('pedido_envios.id'), primary_key=True)
    pedido_linea_id: Mapped[int] = mapped_column(ForeignKey('pedido_lineas.id'), primary_key=True)
    cantidad: Mapped[int] = mapped_column(Integer)
