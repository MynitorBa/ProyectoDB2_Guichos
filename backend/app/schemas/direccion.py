from pydantic import BaseModel


class DireccionCreate(BaseModel):
    tipo: str = 'envio'
    pais: str = 'Guatemala'
    departamento: str
    municipio: str
    linea1: str
    linea2: str | None = None
    codigo_postal: str | None = None
    es_predeterminada: bool = False


class DireccionResponse(BaseModel):
    id: int
    tipo: str
    pais: str
    departamento: str
    municipio: str
    linea1: str
    linea2: str | None
    codigo_postal: str | None
    es_predeterminada: bool
    activa: bool

    model_config = {'from_attributes': True}
