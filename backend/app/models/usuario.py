from datetime import datetime
from sqlalchemy import String, Enum, DateTime, ForeignKey, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db_mysql import Base


class Rol(Base):
    __tablename__ = 'roles'

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(30), unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(120))

    usuarios: Mapped[list['UsuarioRol']] = relationship(back_populates='rol')


class UsuarioRol(Base):
    __tablename__ = 'usuario_rol'

    usuario_id: Mapped[int] = mapped_column(ForeignKey('usuarios.id'), primary_key=True)
    rol_id: Mapped[int] = mapped_column(ForeignKey('roles.id'), primary_key=True)
    asignado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    usuario: Mapped['Usuario'] = relationship(back_populates='usuario_roles')
    rol: Mapped['Rol'] = relationship(back_populates='usuarios')


class Usuario(Base):
    __tablename__ = 'usuarios'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    nombre: Mapped[str] = mapped_column(String(100))
    apellido: Mapped[str] = mapped_column(String(100))
    telefono: Mapped[str | None] = mapped_column(String(20))
    estado: Mapped[str] = mapped_column(
        Enum('activo', 'inactivo', 'suspendido'), default='activo'
    )
    email_verificado: Mapped[bool] = mapped_column(default=False)
    fecha_alta: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    usuario_roles: Mapped[list['UsuarioRol']] = relationship(back_populates='usuario', cascade='all, delete-orphan')
    direcciones: Mapped[list['Direccion']] = relationship(back_populates='usuario')
    pedidos: Mapped[list['Pedido']] = relationship(back_populates='usuario')
    carritos: Mapped[list['Carrito']] = relationship(back_populates='usuario')

    @property
    def roles(self) -> list[Rol]:
        return [ur.rol for ur in self.usuario_roles]


# Importaciones diferidas para evitar ciclos
from app.models.direccion import Direccion  # noqa: E402
from app.models.pedido import Pedido        # noqa: E402
from app.models.carrito import Carrito      # noqa: E402
