from sqlalchemy import String, Enum, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db_mysql import Base


class Direccion(Base):
    __tablename__ = 'direcciones'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id'))
    tipo: Mapped[str] = mapped_column(Enum('envio', 'facturacion'), default='envio')
    pais: Mapped[str] = mapped_column(String(60), default='Guatemala')
    departamento: Mapped[str] = mapped_column(String(60))
    municipio: Mapped[str] = mapped_column(String(60))
    linea1: Mapped[str] = mapped_column(String(200))
    linea2: Mapped[str | None] = mapped_column(String(200))
    codigo_postal: Mapped[str | None] = mapped_column(String(10))
    es_predeterminada: Mapped[bool] = mapped_column(default=False)
    activa: Mapped[bool] = mapped_column(default=True)

    usuario: Mapped['Usuario'] = relationship(back_populates='direcciones')


from app.models.usuario import Usuario  # noqa: E402
