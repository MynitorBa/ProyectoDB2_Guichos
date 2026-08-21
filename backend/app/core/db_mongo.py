from pymongo import MongoClient
from pymongo.database import Database

from app.core.config import settings

_client: MongoClient | None = None


def get_mongo_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(settings.MONGO_URI)
    return _client


def get_mongo_db() -> Database:
    return get_mongo_client()[settings.MONGO_DB]


def close_mongo():
    global _client
    if _client:
        _client.close()
        _client = None
