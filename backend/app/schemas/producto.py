from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Any


class ProductoCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    nombre: str
    descripcion: str | None = None
    precio: Decimal = Field(ge=0)
    categoria_slugs: list[str] = Field(min_length=1)
    atributos: dict[str, Any] = Field(default_factory=dict)
    imagenes: list[str] = Field(default_factory=list)
    stock: int = Field(default=0, ge=0)
    vendedor_usuario_id: int | None = None


class ProductoUpdate(BaseModel):
    nombre: str | None = None
    descripcion: str | None = None
    precio: Decimal | None = Field(default=None, ge=0)
    atributos: dict[str, Any] | None = None
    disponible: bool | None = None
    estado: str | None = None
    stock: int | None = Field(default=None, ge=0)
    imagenes: list[str] | None = None
    vendedor_usuario_id: int | None = None
    categoria_slugs: list[str] | None = None

    @field_validator('categoria_slugs')
    @classmethod
    def categorias_no_vacias(cls, value):
        if value is not None and not value:
            raise ValueError('Debes indicar al menos una categoría.')
        return value


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
