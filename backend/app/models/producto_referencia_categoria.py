from sqlalchemy import ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db_mysql import Base

class ProductoReferenciaCategoria(Base):
    __tablename__ = 'producto_referencia_categorias'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    producto_referencia_id: Mapped[int] = mapped_column(ForeignKey('producto_referencias.id', ondelete='CASCADE'))
    categoria_id: Mapped[int] = mapped_column(ForeignKey('categorias.id'))
    es_principal: Mapped[bool] = mapped_column(Boolean, default=False)
