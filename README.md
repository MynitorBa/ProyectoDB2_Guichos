# TiendaYa — Portal de E-Commerce Políglota

Proyecto del curso **Bases de Datos 2** — UNIS, Segundo Semestre 2026.
Portal de e-commerce con arquitectura políglota: MySQL 8 para datos relacionales y MongoDB 7 para el catálogo de productos con atributos variables.

## Arquitectura actual (Entrega 1)

```
React (Vite) → FastAPI (Python) → MySQL 8  (usuarios, ofertas, pedidos, inventario, outbox)
                                → MongoDB 7 (catálogo documental, proyecciones, eventos)
```

## Requisitos

- Docker Desktop instalado y corriendo
- Python 3.12 (se instala automáticamente en setup si falta)
- Node.js 20+
- Git


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
│  ├─ mysql/                   # DDL, índices, seed y migraciones versionadas
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
# Instalación completa desde cero, incluidas todas las extensiones vigentes
.\scripts\setup.ps1

# Iniciar TiendaYa
.\scripts\start-dev.ps1

# Verificar integridad
cd backend
.\venv\Scripts\python.exe scripts\verify_setup.py

# Correr pruebas
.\venv\Scripts\python.exe -m pytest tests -q

# Compilar frontend
cd ..\frontend
npm run build

# Reinicializar todos los datos (operación destructiva)
cd ..
.\scripts\reset-db.ps1
```

La migración de Fase 1 no elimina datos. Antes de crear las nuevas claves
foráneas comprueba que no existan referencias huérfanas y aborta si encuentra
alguna. Las instalaciones nuevas la ejecutan automáticamente mediante Docker.

La Fase 3 conserva el modelo anterior y llena en paralelo ofertas, precios,
relaciones de inventario, subpedidos por vendedor y snapshots históricos. Es
idempotente: puede repetirse sin duplicar filas.

La Fase 5 hace que MySQL sea la autoridad de precio e inventario. Cada cambio
genera un mensaje transaccional y el worker del backend actualiza de forma
idempotente la proyección del catálogo en MongoDB. Consulte
[`docs/12-fase5-outbox.md`](docs/12-fase5-outbox.md) para ver las garantías y
la evidencia de pruebas.

La Fase 6A retiró la dependencia operativa de los campos duplicados de la tabla
SQL `productos`. Consulte
[`docs/13-fase6a-retiro-logico.md`](docs/13-fase6a-retiro-logico.md) para ver
la preparación previa al corte físico.

La parte aditiva de Fase 6B creó `producto_referencias` y migró reseñas y
movimientos hacia FKs definitivas. El corte físico posterior retiró la tabla
SQL descriptiva `productos`, `producto_imagenes`, las columnas operativas
`producto_id` y el procedimiento de checkout antiguo. Consulte
[`docs/14-fase6b-aditiva.md`](docs/14-fase6b-aditiva.md) y
[`docs/15-fase6b-corte-fisico.md`](docs/15-fase6b-corte-fisico.md).

La extensión de integridad de la Fase 7 enlaza categorías, referencias de
producto y ofertas mediante FKs. En una base ya existente se aplica y valida
con `scripts\complete-phase7-reference-integrity.ps1`. La evidencia está en
[`docs/16-fase7-integridad-referencias.md`](docs/16-fase7-integridad-referencias.md).

La extensión posterior vuelve a incorporar las imágenes binarias bajo la
identidad mínima `producto_referencias` (ya no bajo la tabla eliminada
`productos`) y permite varias categorías por producto. `setup.ps1` aplica la
migración `12_catalog_images_categories.sql` de forma automática e idempotente.
Los detalles y casos de prueba están en
[`docs/20-imagenes-categorias-ofertas.md`](docs/20-imagenes-categorias-ofertas.md).

## Documentación vigente

- [Modelo relacional definitivo](docs/01-modelo-relacional.md)
- [Diagrama ER definitivo](docs/02-diagrama-ER.md)
- [Arquitectura](docs/05-diagrama-arquitectura.md)
- [Referencias MySQL–MongoDB](docs/07-referencia-sql-mongo.md)
- [Informe de Entrega 1](docs/informe-entrega1.md)
- [Plan y evidencia de migración](docs/09-plan-migracion-incremental.md)
- [Evidencia de integridad de referencias](docs/16-fase7-integridad-referencias.md)
- [Pruebas funcionales integrales](docs/17-pruebas-funcionales.md)
- [Guía de revisión para el equipo](docs/18-guia-revision-companeros.md)
- [Correcciones del flujo de instalación](docs/19-correcciones-instalacion.md)
- [Imágenes SQL, categorías múltiples y revisión de ofertas](docs/20-imagenes-categorias-ofertas.md)

## Entregas del proyecto

| Entrega | Estado | Contenido |
|---|---|---|
| **Entrega 1** | **Completada** | MySQL normalizado + migración a MongoDB + historial por eventos |
| Entrega 2 | Pendiente | Redis (carrito, sesiones, caché de catálogo) |
| Entrega 3 | Pendiente | Base de datos columnar/grafos (analytics, recomendaciones) |
| Entrega 4 | Pendiente | Motor de búsqueda + base vectorial (búsqueda semántica) |
