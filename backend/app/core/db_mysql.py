from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings

# pool_pre_ping descarta conexiones muertas antes de usarlas (útil con MySQL en Docker)
engine = create_engine(
    settings.mysql_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# Generador para inyección de sesión MySQL en los endpoints (usado con Depends)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
