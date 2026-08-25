from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel
from typing import Any


class ProductoCreate(BaseModel):
    sku: str | None = None
    nombre: str
    descripcion: str | None = None
    precio: Decimal
    categoria_slugs: list[str]
    atributos: dict[str, Any] = {}
    imagenes: list[str] = []
    stock: int = 0
    vendedor_usuario_id: int | None = None


class ProductoUpdate(BaseModel):
    nombre: str | None = None
    descripcion: str | None = None
    precio: Decimal | None = None
    atributos: dict[str, Any] | None = None
    disponible: bool | None = None
    estado: str | None = None
    stock: int | None = None
    imagenes: list[str] | None = None
    vendedor_usuario_id: int | None = None
    categoria_slugs: list[str] | None = None


class ProductoResponse(BaseModel):
    id: str
    sku: str
    nombre: str
    descripcion: str | None
    precio: float
    categoria: dict
    estado: str
    disponible: bool
    atributos: dict
    imagenes: list
    vendedor_id: str | None
    vendedor_nombre: str | None
    resumen_resenas: dict | None
    fecha_creacion: datetime | None
    fecha_actualizacion: datetime | None

    model_config = {'from_attributes': True}


class ProductoListResponse(BaseModel):
    items: list[dict]
    total: int
    page: int
    page_size: int
    total_pages: int
