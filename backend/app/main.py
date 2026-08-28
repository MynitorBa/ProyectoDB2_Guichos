import os
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import ENCODERS_BY_TYPE
from bson import ObjectId
from bson.decimal128 import Decimal128

# Enseña a FastAPI a serializar tipos BSON que pymongo devuelve en documentos MongoDB
ENCODERS_BY_TYPE[ObjectId] = str
ENCODERS_BY_TYPE[Decimal128] = lambda d: float(d.to_decimal())

from app.core.config import settings
from app.core.db_mongo import close_mongo, ensure_indexes, get_mongo_db
from app.services.outbox_service import start_outbox_worker, stop_outbox_worker
from app.api.v1 import auth, addresses, categories, products, orders, cart, admin, notifications, vendor, catalog_requests


logger = logging.getLogger(__name__)

app = FastAPI(
    title='TiendaYa API',
    version='1.0.0',
    description='Portal de e-commerce — Bases de Datos 2, UNIS',
)

# CORS: permite peticiones del frontend (Vite en :5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        'http://localhost:5173',
        'http://127.0.0.1:5173',
    ],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Manejo centralizado de errores — no filtra stack traces al cliente
@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.error(
        'Error no controlado en %s %s', request.method, request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    origin = request.headers.get('origin', '')
    allowed_origins = [
        settings.FRONTEND_URL,
        'http://localhost:5173',
        'http://127.0.0.1:5173',
    ]
    response = JSONResponse(
        status_code=500,
        content={'detail': 'Error interno del servidor.', 'code': 'INTERNAL_ERROR'},
    )
    # Algunos errores 500 bypass la CORSMiddleware; se agregan las cabeceras
    # manualmente para que el frontend siempre pueda leer la respuesta de error.
    if origin in allowed_origins:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response


# Archivos estáticos (imágenes de productos)
os.makedirs('static/products', exist_ok=True)
app.mount('/static', StaticFiles(directory='static'), name='static')

# Routers
app.include_router(auth.router,       prefix='/api/v1')
app.include_router(addresses.router,  prefix='/api/v1')
app.include_router(categories.router, prefix='/api/v1')
app.include_router(products.router,   prefix='/api/v1')
app.include_router(orders.router,     prefix='/api/v1')
app.include_router(cart.router,       prefix='/api/v1')
app.include_router(admin.router,         prefix='/api/v1')
app.include_router(notifications.router, prefix='/api/v1')
app.include_router(vendor.router,        prefix='/api/v1')
app.include_router(catalog_requests.vendor_router, prefix='/api/v1')
app.include_router(catalog_requests.admin_router, prefix='/api/v1')


# Al arrancar: crea índices en Mongo y lanza el worker del patrón Outbox
@app.on_event('startup')
def startup():
    ensure_indexes(get_mongo_db())
    start_outbox_worker()


@app.on_event('shutdown')
def shutdown():
    stop_outbox_worker()
    close_mongo()


@app.get('/health')
def health():
    return {'status': 'ok', 'version': '1.0.0'}
