from pydantic_settings import BaseSettings, SettingsConfigDict


# Todas las variables se pueden sobreescribir con un archivo .env en la raíz del backend
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    # MySQL
    MYSQL_HOST: str = 'localhost'
    MYSQL_PORT: int = 3306
    MYSQL_DB: str = 'tiendaya'
    MYSQL_USER: str = 'tiendaya'
    MYSQL_PASSWORD: str = 'tiendaya123'

    @property
    def mysql_url(self) -> str:
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}"
            f"?charset=utf8mb4"
        )

    # MongoDB
    MONGO_URI: str = 'mongodb://admin:adminpassword@localhost:27017/tiendaya?authSource=admin'
    MONGO_DB: str = 'tiendaya'

    # JWT
    SECRET_KEY: str = 'CAMBIA_ESTO_EN_PRODUCCION_clave_secreta_muy_larga'
    ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # CORS
    FRONTEND_URL: str = 'http://localhost:5173'

    # Server
    BACKEND_HOST: str = '0.0.0.0'
    BACKEND_PORT: int = 8000

    # Email (SMTP) — dejar vacío para deshabilitar envío de correos
    SMTP_HOST: str = 'smtp.gmail.com'
    SMTP_PORT: int = 587
    SMTP_USER: str = ''
    SMTP_PASSWORD: str = ''
    SMTP_FROM_NAME: str = 'TiendaYa'


settings = Settings()
