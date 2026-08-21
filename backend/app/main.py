from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.db_mongo import close_mongo, ensure_indexes, get_mongo_db
from app.api.v1 import auth, addresses, categories, products, orders, cart, admin

app = FastAPI(
    title='TiendaYa API',
    version='1.0.0',
    description='Portal de e-commerce — Bases de Datos 2, UNIS',
)

# CORS: permite peticiones del frontend (Vite en :5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, 'http://localhost:5173'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Manejo centralizado de errores — no filtra stack traces al cliente
@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={'detail': 'Error interno del servidor.', 'code': 'INTERNAL_ERROR'},
    )


# Routers
app.include_router(auth.router,       prefix='/api/v1')
app.include_router(addresses.router,  prefix='/api/v1')
app.include_router(categories.router, prefix='/api/v1')
app.include_router(products.router,   prefix='/api/v1')
app.include_router(orders.router,     prefix='/api/v1')
app.include_router(cart.router,       prefix='/api/v1')
app.include_router(admin.router,      prefix='/api/v1')


@app.on_event('startup')
def startup():
    ensure_indexes(get_mongo_db())


@app.on_event('shutdown')
def shutdown():
    close_mongo()


@app.get('/health')
def health():
    return {'status': 'ok', 'version': '1.0.0'}
