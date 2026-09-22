"""Endpoints de reseñas — Neo4j como fuente de verdad."""
from __future__ import annotations
import os, uuid as _uuid
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from neo4j import Session as Neo4jSession

STATIC_REVIEWS_DIR = "static/reviews"
ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

from app.core.deps import get_current_user, get_optional_user, require_role, get_db, get_neo4j
from app.models.usuario import Usuario
from app.models.vendedor import Vendedor
from app.services import review_service as svc
from app.services import fraud_detection_service as fraud

router = APIRouter(prefix='/reviews', tags=['Reseñas'])
get_admin = require_role('administrador')


class ResenaCreate(BaseModel):
    producto_ref: str = Field(min_length=24, max_length=24)
    vendedor_id: int
    calificacion: int = Field(ge=1, le=5)
    texto: str = Field(min_length=5, max_length=1000)


class RespuestaCreate(BaseModel):
    texto: str = Field(min_length=1, max_length=1000)


@router.get('/puede-opinar/{producto_ref}')
def puede_opinar(
    producto_ref: str,
    user: Usuario = Depends(get_current_user),
    neo4j: Neo4jSession = Depends(get_neo4j),
):
    compro = svc.verificar_compra(neo4j, user.id, producto_ref)
    ya     = svc.ya_reseno(neo4j, user.id, producto_ref)
    return {"puede": compro and not ya, "compro": compro, "ya_reseno": ya}


@router.post('', status_code=201)
def crear_resena(
    payload: ResenaCreate,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
    neo4j: Neo4jSession = Depends(get_neo4j),
):
    if not svc.verificar_compra(neo4j, user.id, payload.producto_ref):
        raise HTTPException(403, 'Solo puedes opinar sobre productos que hayas comprado.')
    if svc.ya_reseno(neo4j, user.id, payload.producto_ref):
        raise HTTPException(409, 'Ya escribiste una reseña para este producto.')
    vendedor = db.get(Vendedor, payload.vendedor_id)
    if not vendedor:
        raise HTTPException(404, 'Vendedor no encontrado.')
    # Intentar obtener nombre del producto desde MongoDB sería ideal,
    # pero usamos un placeholder que el servicio puede actualizar después.
    resena = svc.crear_resena(
        neo4j,
        user_id=user.id,
        nombre_usuario=f"{user.nombre} {user.apellido}".strip(),
        email_usuario=user.email,
        producto_ref=payload.producto_ref,
        nombre_producto=payload.producto_ref,  # se actualiza al listar
        vendedor_id=vendedor.id,
        nombre_vendedor=vendedor.nombre_comercial,
        calificacion=payload.calificacion,
        texto=payload.texto,
    )
    return resena


@router.get('/mi-vendedor')
def mi_perfil_vendedor(
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vendedor = db.query(Vendedor).filter(Vendedor.usuario_id == user.id).first()
    return {"vendedor_id": vendedor.id if vendedor else None}


@router.post('/{resena_id}/imagenes', status_code=201)
async def subir_imagenes(
    resena_id: str,
    archivos: list[UploadFile] = File(...),
    user: Usuario = Depends(get_current_user),
    neo4j: Neo4jSession = Depends(get_neo4j),
):
    if len(archivos) > 4:
        raise HTTPException(400, 'Máximo 4 imágenes por reseña.')
    os.makedirs(STATIC_REVIEWS_DIR, exist_ok=True)
    urls = []
    for archivo in archivos:
        ext = os.path.splitext(archivo.filename or '')[1].lower()
        if ext not in ALLOWED_EXTS:
            raise HTTPException(400, f'Formato no permitido: {ext or "desconocido"}')
        filename = f"{resena_id}_{_uuid.uuid4().hex}{ext}"
        content = await archivo.read()
        with open(os.path.join(STATIC_REVIEWS_DIR, filename), 'wb') as f:
            f.write(content)
        urls.append(f"/static/reviews/{filename}")
    if urls:
        svc.agregar_imagenes_resena(neo4j, resena_id, user.id, urls)
    return {"imagenes": urls}


@router.post('/{resena_id}/respuestas', status_code=201)
def crear_respuesta(
    resena_id: str,
    payload: RespuestaCreate,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
    neo4j: Neo4jSession = Depends(get_neo4j),
):
    vendedor = db.query(Vendedor).filter(Vendedor.usuario_id == user.id).first()
    if not vendedor:
        raise HTTPException(403, 'Solo el vendedor del producto puede responder a las reseñas.')
    try:
        return svc.crear_respuesta(
            neo4j,
            user_id=user.id,
            nombre_usuario=f"{user.nombre} {user.apellido}".strip(),
            resena_id=resena_id,
            texto=payload.texto,
            vendedor_id=vendedor.id,
        )
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError:
        raise HTTPException(404, 'Reseña no encontrada.')


@router.patch('/{resena_id}/estado')
def moderar(
    resena_id: str,
    estado: str = Query(enum=['aprobada', 'rechazada', 'pendiente']),
    _: Usuario = Depends(get_admin),
    neo4j: Neo4jSession = Depends(get_neo4j),
):
    ok = svc.moderar_resena(neo4j, resena_id, estado)
    if not ok:
        raise HTTPException(404, 'Reseña no encontrada.')
    return {"ok": True}


@router.get('/admin/fraude/resumen')
def fraude_resumen(
    _: Usuario = Depends(get_admin),
    neo4j: Neo4jSession = Depends(get_neo4j),
):
    return fraud.resumen_fraude(neo4j)


@router.get('/admin/fraude/bombardeo')
def fraude_bombardeo(
    ventana_horas: int = Query(24, ge=1, le=168),
    umbral: int = Query(5, ge=2),
    _: Usuario = Depends(get_admin),
    neo4j: Neo4jSession = Depends(get_neo4j),
):
    return fraud.detectar_bombardeo(neo4j, ventana_horas, umbral)


@router.get('/admin/fraude/sin-compra')
def fraude_sin_compra(
    _: Usuario = Depends(get_admin),
    neo4j: Neo4jSession = Depends(get_neo4j),
):
    return fraud.detectar_sin_compra(neo4j)


@router.get('/admin/fraude/reviewer-unico-vendedor')
def fraude_unico_vendedor(
    min_resenas: int = Query(3, ge=2),
    _: Usuario = Depends(get_admin),
    neo4j: Neo4jSession = Depends(get_neo4j),
):
    return fraud.detectar_reviewer_unico_vendedor(neo4j, min_resenas)


@router.get('/admin/fraude/cluster')
def fraude_cluster(
    min_comun: int = Query(3, ge=2),
    _: Usuario = Depends(get_admin),
    neo4j: Neo4jSession = Depends(get_neo4j),
):
    return fraud.detectar_cluster_coordinado(neo4j, min_comun)


@router.get('/{producto_ref}')
def listar_resenas(
    producto_ref: str,
    todas: bool = Query(False),
    neo4j: Neo4jSession = Depends(get_neo4j),
    user: Usuario | None = Depends(get_optional_user),
):
    user_id = user.id if user else None
    resenas = svc.listar_resenas(neo4j, producto_ref, solo_aprobadas=not todas, user_id=user_id)
    resumen = svc.resumen_calificaciones(neo4j, producto_ref)
    return {"resumen": resumen, "resenas": resenas}
