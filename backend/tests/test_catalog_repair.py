import os

from dotenv import load_dotenv
from pymongo import MongoClient

from scripts.repair_catalog_data import validate_attributes


load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))


def test_all_catalog_documents_match_their_category_schemas():
    client = MongoClient(os.getenv('MONGO_URI'), serverSelectionTimeoutMS=5000)
    try:
        mongo = client[os.getenv('MONGO_DB', 'tiendaya')]
        schemas = {
            row['categoria_slug']: row
            for row in mongo.categoria_esquemas.find({})
        }
        problems = {}
        for doc in mongo.productos.find({}):
            errors = validate_attributes(doc, schemas)
            if errors:
                problems[doc.get('sku', str(doc['_id']))] = errors
        assert problems == {}
    finally:
        client.close()


def test_legacy_mysql_id_was_removed_from_documental_catalog():
    client = MongoClient(os.getenv('MONGO_URI'), serverSelectionTimeoutMS=5000)
    try:
        mongo = client[os.getenv('MONGO_DB', 'tiendaya')]
        assert mongo.productos.count_documents({'mysql_id': {'$exists': True}}) == 0
    finally:
        client.close()
