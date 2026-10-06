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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # CORS
    FRONTEND_URL: str = 'http://localhost:5173'

    # Server
    BACKEND_HOST: str = '0.0.0.0'
    BACKEND_PORT: int = 8000

    # Redis
    REDIS_HOST: str = 'localhost'
    REDIS_PORT: int = 6379
    REDIS_CART_TTL: int = 1800  # segundos de inactividad antes de expirar el carrito

    # Cassandra (proyección analítica; nunca participa en el checkout transaccional)
    CASSANDRA_HOST: str = 'localhost'
    CASSANDRA_PORT: int = 9042
    CASSANDRA_KEYSPACE: str = 'tiendaya_analytics'
    CASSANDRA_LOCAL_DC: str = 'datacenter1'

    # Neo4j (grafo de reseñas y detección de fraude)
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "tiendaya123"

    # Elasticsearch (índice de búsqueda; proyección reconstruible del catálogo)
    # 127.0.0.1 y no localhost: en Windows, localhost intenta IPv6 primero y
    # agrega ~40 ms a cada consulta.
    ES_URL: str = 'http://127.0.0.1:9200'
    ES_INDEX_ALIAS: str = 'productos'  # alias estable; apunta a productos_vN
    ES_TIMEOUT: float = 1.5  # segundos; si se excede, la búsqueda usa MongoDB

    # Pasarela de pagos (simulada en payment_simulator/, proceso aparte)
    PAYMENT_GATEWAY_URL: str = 'http://127.0.0.1:8001'
    PAYMENT_TIMEOUT: float = 3.0  # segundos por intento; después el resultado es "desconocido"
    PAYMENT_RETRIES: int = 2  # reintentos seguros con la misma clave idempotente
    # Tiempo máximo que un pedido puede retener inventario esperando su pago.
    CHECKOUT_RESERVA_MINUTOS: int = 10

    # Email (SMTP) — dejar vacío para deshabilitar envío de correos
    SMTP_HOST: str = 'smtp.gmail.com'
    SMTP_PORT: int = 587
    SMTP_USER: str = ''
    SMTP_PASSWORD: str = ''
    SMTP_FROM_NAME: str = 'TiendaYa'


settings = Settings()
