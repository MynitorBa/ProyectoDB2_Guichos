# TiendaYa — Portal de E-Commerce Políglota

Proyecto del curso **Bases de Datos 2** — UNIS, Segundo Semestre 2026.
Portal de e-commerce con arquitectura políglota: MySQL 8 para datos relacionales y MongoDB 7 para el catálogo de productos con atributos variables.

## Arquitectura actual (Entrega 1)

```
React (Vite) → FastAPI (Python) → MySQL 8  (usuarios, pedidos, inventario)
                                → MongoDB 7 (catálogo de productos, eventos)
```

## Requisitos

- Docker Desktop instalado y corriendo
- Python 3.12 (se instala automáticamente en setup si falta)
- Node.js 20+
- Git

## Instalación rápida

```powershell
# 1. Clonar o ubicarse en la carpeta del proyecto
cd "C:\Users\mynit\OneDrive\Escritorio\UNIS\Segundo Semestre 2026\Bases de Datos 2\proyecto"

# 2. Setup completo (solo la primera vez o después de reset)
.\scripts\setup.ps1

# 3. Arrancar el sistema
.\scripts\start-dev.ps1
```

## URLs del sistema

| Servicio | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Adminer (MySQL) | http://localhost:8080 |
| Mongo Express | http://localhost:8081 |

## Credenciales de prueba

| Rol | Email | Contraseña |
|---|---|---|
| Administrador | admin@tiendaya.gt | password123 |
| Comprador | comprador1@gmail.com | password123 |
| Vendedor | vendedor1@tiendaya.gt | password123 |

> **IMPORTANTE**: La contraseña `password123` ya está hasheada con bcrypt en el seed SQL. No es necesario cambiarla para las pruebas.

## Estructura del proyecto

```
proyecto/
├─ docker-compose.yml          # MySQL, MongoDB, Adminer, Mongo Express
├─ database/
│  ├─ mysql/                   # DDL, índices, stored procedure, seed
│  └─ mongo/                   # Init collections, índices, ejemplos aggregation
├─ backend/                    # FastAPI + Python
│  ├─ app/
│  │  ├─ api/v1/               # Endpoints REST
│  │  ├─ services/             # checkout_service, catalog_service, product_history_service
│  │  └─ models/               # SQLAlchemy ORM
│  └─ scripts/                 # migrate, seed_events, verify
├─ frontend/                   # React + Vite
│  └─ src/pages/               # CatalogPage, ProductDetailPage, AdminPage, ProductHistoryPage...
├─ docs/                       # ADRs, diagramas, informe
└─ scripts/                    # setup.ps1, start-dev.ps1, reset-db.ps1
```

## Comandos útiles

```powershell
# Resetear todo (borra datos)
.\scripts\reset-db.ps1

# Solo migrar productos a Mongo (idempotente)
cd backend
.\venv\Scripts\python.exe scripts\migrate_products_to_mongo.py

# Regenerar historial de eventos
.\venv\Scripts\python.exe scripts\seed_mongo_events.py

# Verificar integridad
.\venv\Scripts\python.exe scripts\verify_setup.py

# Correr pruebas
.\venv\Scripts\pytest.exe tests/ -v
```

## Entregas del proyecto

| Entrega | Estado | Contenido |
|---|---|---|
| **Entrega 1** | **Completada** | MySQL normalizado + migración a MongoDB + historial por eventos |
| Entrega 2 | Pendiente | Redis (carrito, sesiones, caché de catálogo) |
| Entrega 3 | Pendiente | Base de datos columnar/grafos (analytics, recomendaciones) |
| Entrega 4 | Pendiente | Motor de búsqueda + base vectorial (búsqueda semántica) |
