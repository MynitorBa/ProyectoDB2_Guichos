from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, DECIMAL, Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_mysql import Base
from app.core.time import utc_now


# Flujo de aprobación para que un vendedor añada un producto nuevo o una oferta sobre uno existente
class SolicitudCatalogo(Base):
    __tablename__ = 'solicitudes_catalogo'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    vendedor_id: Mapped[int] = mapped_column(ForeignKey('vendedores.id'))
    tipo: Mapped[str] = mapped_column(
        Enum('producto_nuevo', 'oferta_existente')
    )
    estado: Mapped[str] = mapped_column(
        Enum('pendiente', 'aprobada', 'rechazada', 'cancelada'),
        default='pendiente',
    )
    producto_ref_solicitado: Mapped[str | None] = mapped_column(
        ForeignKey('producto_referencias.producto_ref'), nullable=True
    )
    nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    atributos: Mapped[dict] = mapped_column(JSON, default=dict)
    sku_propuesto: Mapped[str | None] = mapped_column(String(50), nullable=True)
    variante_color: Mapped[str] = mapped_column(String(50), default='', server_default='')
    variante_talla: Mapped[str] = mapped_column(String(20), default='', server_default='')
    precio_propuesto: Mapped[Decimal] = mapped_column(DECIMAL(12, 2))
    stock_propuesto: Mapped[int] = mapped_column(Integer)
    observaciones_vendedor: Mapped[str | None] = mapped_column(Text, nullable=True)
    observaciones_admin: Mapped[str | None] = mapped_column(Text, nullable=True)
    revisada_por: Mapped[int | None] = mapped_column(
        ForeignKey('usuarios.id'), nullable=True
    )
    producto_ref_resultado: Mapped[str | None] = mapped_column(
        ForeignKey('producto_referencias.producto_ref'), nullable=True
    )
    oferta_id_resultado: Mapped[int | None] = mapped_column(
        ForeignKey('ofertas.id'), nullable=True
    )
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )
    fecha_revision: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# Categorías propuestas para la solicitud; la restricción de orden garantiza la posición en la galería
class SolicitudCatalogoCategoria(Base):
    __tablename__ = 'solicitud_catalogo_categorias'
    __table_args__ = (
        UniqueConstraint('solicitud_id', 'categoria_id', name='uq_scc_solicitud_categoria'),
        UniqueConstraint('solicitud_id', 'orden', name='uq_scc_solicitud_orden'),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    solicitud_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey('solicitudes_catalogo.id', ondelete='CASCADE')
    )
    categoria_id: Mapped[int] = mapped_column(
        ForeignKey('categorias.id', ondelete='RESTRICT')
    )
    orden: Mapped[int] = mapped_column(Integer, default=0)


# Imágenes subidas durante la solicitud; se transfieren al producto si la solicitud es aprobada
class SolicitudCatalogoImagen(Base):
    __tablename__ = 'solicitud_catalogo_imagenes'
    __table_args__ = (
        UniqueConstraint('solicitud_id', 'orden', name='uq_sci_solicitud_orden'),
        UniqueConstraint('producto_imagen_id', name='uq_sci_imagen'),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    solicitud_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey('solicitudes_catalogo.id', ondelete='CASCADE')
    )
    producto_imagen_id: Mapped[int] = mapped_column(
        ForeignKey('producto_imagenes.id', ondelete='CASCADE')
    )
    orden: Mapped[int] = mapped_column(Integer, default=0)
