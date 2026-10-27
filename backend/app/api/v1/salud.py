from fastapi import APIRouter

from app.core import salud

router = APIRouter(prefix='/salud', tags=['Salud'])


# Estado de cada motor ('ok', 'degradado' o 'caido') para el aviso de la tienda.
# Es público y no expone errores internos; el resultado se reutiliza unos segundos.
@router.get('/motores')
def estado_motores():
    return salud.sondear()
