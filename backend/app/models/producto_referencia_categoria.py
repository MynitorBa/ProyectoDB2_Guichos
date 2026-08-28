from sqlalchemy import Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db_mysql import Base

# Relación N:M entre producto y categorías; es_principal marca la categoría principal para filtros y navegación
class ProductoReferenciaCategoria(Base):
    __tablename__ = 'producto_referencia_categorias'
    __table_args__ = (
        UniqueConstraint(
            'producto_referencia_id', 'categoria_id',
            name='uq_prc_referencia_categoria',
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    producto_referencia_id: Mapped[int] = mapped_column(ForeignKey('producto_referencias.id', ondelete='CASCADE'))
    categoria_id: Mapped[int] = mapped_column(
        ForeignKey('categorias.id', ondelete='RESTRICT')
    )
    es_principal: Mapped[bool] = mapped_column(Boolean, default=False)
