"""Reseñas autoritativas en MySQL y señales relacionales proyectadas en Neo4j."""
from __future__ import annotations
import os, uuid as _uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from neo4j import Session as Neo4jSession

# reviews.py vive en backend/app/api/v1; parents[3] es la raíz de backend,
# que es exactamente el directorio `static` montado por FastAPI.
BACKEND_DIR = Path(__file__).resolve().parents[3]
STATIC_REVIEWS_DIR = BACKEND_DIR / "static" / "reviews"
ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

from app.core.deps import get_current_user, get_optional_user, require_role, get_db, get_neo4j, get_neo4j_opcional
from app.models.usuario import Usuario
from app.models.vendedor import Vendedor
from app.models.resena import Resena
from app.models.producto_referencia import ProductoReferencia
from app.services import review_mysql_service as mysql_svc
from app.services.outbox_service import encolar_resena
from app.services import fraud_detection_service as fraud
from app.services.fraud_analysis_service import (
    FraudAnalysisBusy, fraud_analysis_status, run_fraud_analysis_once,
)

router = APIRouter(prefix='/reviews', tags=['Reseñas'])
get_admin = require_role('administrador')


class ResenaCreate(BaseModel):
    producto_ref: str = Field(min_length=24, max_length=24)
    vendedor_id: int
    calificacion: int = Field(ge=1, le=5)
    texto: str = Field(min_length=5, max_length=1000)


class RespuestaCreate(BaseModel):
    texto: str = Field(min_length=1, max_length=1000)


class ResenaUpdate(BaseModel):
    calificacion: int = Field(ge=1, le=5)
    texto: str = Field(min_length=5, max_length=1000)


class AlertaUpdate(BaseModel):
    estado: str = Field(pattern='^(pendiente|en_revision|descartada|revisada)$')
    notas: str | None = Field(default=None, max_length=2000)


@router.get('/puede-opinar/{producto_ref}')
def puede_opinar(
    producto_ref: str,
    vendedor_id: int = Query(..., gt=0),
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return mysql_svc.elegibilidad(
        db, usuario_id=user.id, producto_ref=producto_ref, vendedor_id=vendedor_id,
    )


@router.post('', status_code=201)
def crear_resena(
    payload: ResenaCreate,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vendedor = db.get(Vendedor, payload.vendedor_id)
    if not vendedor:
        raise HTTPException(404, 'Vendedor no encontrado.')
    try:
        review = mysql_svc.crear(
            db, usuario_id=user.id, producto_ref=payload.producto_ref,
            vendedor_id=vendedor.id, calificacion=payload.calificacion,
            texto=payload.texto,
        )
        encolar_resena(
            db, tipo_evento='resena.creada', resena_id=review.id,
            producto_ref=payload.producto_ref,
        )
        db.commit()
        db.refresh(review)
        return mysql_svc.serializar(db, review)
    except PermissionError as exc:
        db.rollback()
        raise HTTPException(403, str(exc))
    except FileExistsError as exc:
        db.rollback()
        raise HTTPException(409, str(exc))
    except LookupError as exc:
        db.rollback()
        raise HTTPException(404, str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Ya existe una reseña para ese producto y vendedor.')


@router.put('/{resena_id}')
def editar_resena(
    resena_id: str,
    payload: ResenaUpdate,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        review = mysql_svc.editar(
            db, public_id=resena_id, usuario_id=user.id,
            calificacion=payload.calificacion, texto=payload.texto,
        )
        ref = review.producto_referencia_id
        product = db.get(ProductoReferencia, ref)
        producto_ref = product.producto_ref
        encolar_resena(
            db, tipo_evento='resena.actualizada', resena_id=review.id,
            producto_ref=producto_ref,
        )
        db.commit()
        db.refresh(review)
        return mysql_svc.serializar(db, review)
    except PermissionError as exc:
        db.rollback()
        raise HTTPException(403, str(exc))
    except LookupError as exc:
        db.rollback()
        raise HTTPException(404, str(exc))


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
    db: Session = Depends(get_db),
):
    if len(archivos) > 4:
        raise HTTPException(400, 'Máximo 4 imágenes por reseña.')
    STATIC_REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    urls = []
    for archivo in archivos:
        ext = os.path.splitext(archivo.filename or '')[1].lower()
        if ext not in ALLOWED_EXTS:
            raise HTTPException(400, f'Formato no permitido: {ext or "desconocido"}')
        filename = f"{resena_id}_{_uuid.uuid4().hex}{ext}"
        content = await archivo.read()
        with (STATIC_REVIEWS_DIR / filename).open('wb') as f:
            f.write(content)
        urls.append(f"/static/reviews/{filename}")
    if urls:
        try:
            mysql_svc.agregar_imagenes(
                db, public_id=resena_id, usuario_id=user.id, urls=urls,
            )
            review = db.query(Resena).filter_by(public_id=resena_id).first()
            producto_ref = db.get(ProductoReferencia, review.producto_referencia_id).producto_ref
            encolar_resena(
                db, tipo_evento='resena.actualizada', resena_id=review.id,
                producto_ref=producto_ref,
            )
            db.commit()
        except (LookupError, ValueError) as exc:
            db.rollback()
            for url in urls:
                try:
                    (BACKEND_DIR / url.lstrip('/')).unlink(missing_ok=True)
                except OSError:
                    pass
            raise HTTPException(404 if isinstance(exc, LookupError) else 400, str(exc))
    return {"imagenes": urls}


@router.post('/{resena_id}/respuestas', status_code=201)
def crear_respuesta(
    resena_id: str,
    payload: RespuestaCreate,
    user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vendedor = db.query(Vendedor).filter(Vendedor.usuario_id == user.id).first()
    if not vendedor:
        raise HTTPException(403, 'Solo el vendedor del producto puede responder a las reseñas.')
    try:
        reply = mysql_svc.responder(
            db, public_id=resena_id, usuario_id=user.id,
            vendedor_id=vendedor.id, texto=payload.texto,
        )
        review = db.query(Resena).filter(Resena.public_id == resena_id).first()
        producto_ref = db.get(ProductoReferencia, review.producto_referencia_id).producto_ref
        encolar_resena(
            db, tipo_evento='resena.respuesta_creada', resena_id=review.id,
            producto_ref=producto_ref,
        )
        db.commit()
        return {
            'id': reply.public_id, 'texto': reply.texto,
            'fecha': reply.fecha_creacion.isoformat(), 'es_vendedor': True,
            'autor_nombre': f'{user.nombre} {user.apellido}'.strip(),
        }
    except PermissionError as e:
        db.rollback()
        raise HTTPException(403, str(e))
    except (ValueError, LookupError):
        db.rollback()
        raise HTTPException(404, 'Reseña no encontrada.')


@router.patch('/{resena_id}/estado')
def moderar(
    resena_id: str,
    estado: str = Query(enum=['aprobada', 'rechazada', 'pendiente']),
    _: Usuario = Depends(get_admin),
    db: Session = Depends(get_db),
):
    review = mysql_svc.moderar(db, public_id=resena_id, estado=estado)
    if not review:
        raise HTTPException(404, 'Reseña no encontrada.')
    producto_ref = db.get(ProductoReferencia, review.producto_referencia_id).producto_ref
    encolar_resena(
        db, tipo_evento='resena.moderada', resena_id=review.id,
        producto_ref=producto_ref, payload={'estado': estado},
    )
    db.commit()
    return {"ok": True}


@router.get('/admin/fraude/resumen')
def fraude_resumen(
    _: Usuario = Depends(get_admin),
    db: Session = Depends(get_db),
    neo4j: Neo4jSession | None = Depends(get_neo4j_opcional),
):
    # Plan B de Neo4j: sin el grafo, F01–F03 quedan pendientes y el resto
    # (F04 y los expedientes F05–F07 guardados en MySQL) se sigue mostrando.
    if neo4j is None:
        summary = {clave: {'count': None, 'items': [], 'pendiente': True} for clave in (
            'bombardeo', 'bombardeo_historico', 'reviewer_unico_vendedor',
            'reviewer_unico_vendedor_historico', 'cluster_coordinado', 'cluster_coordinado_historico',
        )}
    else:
        summary = fraud.resumen_fraude(neo4j)
    summary['grafo_disponible'] = neo4j is not None
    f04 = fraud.listar_sin_compra_mysql(db, pagina=1, tamano=5)
    if neo4j is not None:
        fraud.enriquecer_nombres_producto(neo4j, f04['items'])
    summary['sin_compra_verificada'] = {
        'count': f04['total'], 'items': f04['items'],
    }
    summary.update(fraud.resumen_alertas_comerciales(db))
    return summary


@router.get('/admin/fraude/indicadores/{regla}')
def fraude_indicador_paginado(
    regla: str,
    pagina: int = Query(1, ge=1),
    tamano: int = Query(20, enum=[10, 20, 50]),
    buscar: str | None = Query(None, max_length=120),
    segmento: str = Query('verificadas_publicas', pattern='^(verificadas_publicas|historicas_no_verificadas)$'),
    ventana_horas: int = Query(24, ge=1, le=168),
    umbral: int = Query(5, ge=2),
    min_resenas: int = Query(3, ge=2),
    min_comun: int = Query(3, ge=2),
    _: Usuario = Depends(get_admin),
    db: Session = Depends(get_db),
    neo4j: Neo4jSession = Depends(get_neo4j),
):
    if regla not in {'bombardeo', 'sin_compra', 'reviewer_unico_vendedor', 'cluster'}:
        raise HTTPException(404, 'Indicador de fraude desconocido.')
    if regla == 'sin_compra':
        result = fraud.listar_sin_compra_mysql(
            db, pagina=pagina, tamano=tamano, buscar=buscar,
        )
        fraud.enriquecer_nombres_producto(neo4j, result['items'])
        return result
    result = fraud.listar_indicador_paginado(
        neo4j, regla, pagina=pagina, tamano=tamano, buscar=buscar,
        segmento=segmento, ventana_horas=ventana_horas, umbral=umbral,
        min_resenas=min_resenas, min_comun=min_comun,
    )
    fraud.enriquecer_resenas_indicador(db, regla, result['items'])
    return result


@router.get('/admin/fraude/bombardeo')
def fraude_bombardeo(
    ventana_horas: int = Query(24, ge=1, le=168),
    umbral: int = Query(5, ge=2),
    segmento: str = Query('verificadas_publicas', pattern='^(verificadas_publicas|historicas_no_verificadas)$'),
    _: Usuario = Depends(get_admin),
    neo4j: Neo4jSession = Depends(get_neo4j),
):
    return fraud.detectar_bombardeo(neo4j, ventana_horas, umbral, segmento)


@router.get('/admin/fraude/sin-compra')
def fraude_sin_compra(
    _: Usuario = Depends(get_admin),
    neo4j: Neo4jSession = Depends(get_neo4j),
):
    return fraud.detectar_sin_compra(neo4j)


@router.get('/admin/fraude/reviewer-unico-vendedor')
def fraude_unico_vendedor(
    min_resenas: int = Query(3, ge=2),
    segmento: str = Query('verificadas_publicas', pattern='^(verificadas_publicas|historicas_no_verificadas)$'),
    _: Usuario = Depends(get_admin),
    neo4j: Neo4jSession = Depends(get_neo4j),
):
    return fraud.detectar_reviewer_unico_vendedor(neo4j, min_resenas, segmento)


@router.get('/admin/fraude/cluster')
def fraude_cluster(
    min_comun: int = Query(3, ge=2),
    segmento: str = Query('verificadas_publicas', pattern='^(verificadas_publicas|historicas_no_verificadas)$'),
    _: Usuario = Depends(get_admin),
    neo4j: Neo4jSession = Depends(get_neo4j),
):
    return fraud.detectar_cluster_coordinado(neo4j, min_comun, segmento)


@router.get('/admin/fraude/autocompras')
def fraude_autocompras(
    ventana_dias: int = Query(30, ge=1, le=365),
    historico: bool = Query(False),
    _: Usuario = Depends(get_admin),
    neo4j: Neo4jSession = Depends(get_neo4j),
):
    return fraud.detectar_autocompras(
        neo4j, ventana_dias=ventana_dias, historico=historico,
    )


@router.post('/admin/fraude/recalcular')
def fraude_recalcular(
    _: Usuario = Depends(get_admin),
):
    try:
        return run_fraud_analysis_once('manual')
    except FraudAnalysisBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, 'El análisis no pudo completarse; no se inactivaron alertas.') from exc


@router.get('/admin/fraude/estado-analisis')
def fraude_estado_analisis(
    _: Usuario = Depends(get_admin),
    db: Session = Depends(get_db),
):
    return fraud_analysis_status(db)


@router.get('/admin/fraude/alertas')
def fraude_alertas(
    estado: str | None = Query(None),
    _: Usuario = Depends(get_admin),
    db: Session = Depends(get_db),
):
    return fraud.listar_alertas(db, estado)


@router.get('/admin/fraude/alertas-paginadas')
def fraude_alertas_paginadas(
    pagina: int = Query(1, ge=1),
    tamano: int = Query(20, enum=[10, 20, 50]),
    buscar: str | None = Query(None, max_length=120),
    tipo: str | None = Query(None, pattern='^(autocompra|inventario_atipico|coincidencia_cantidad)$'),
    prioridad: str | None = Query(None, pattern='^(informativa|baja|media|alta)$'),
    estado: str | None = Query(None, pattern='^(pendiente|en_revision|descartada|revisada)$'),
    activa: bool | None = Query(None),
    orden: str = Query('fecha_desc', pattern='^(fecha_desc|prioridad_desc)$'),
    _: Usuario = Depends(get_admin),
    db: Session = Depends(get_db),
):
    return fraud.listar_alertas_paginadas(
        db, pagina=pagina, tamano=tamano, buscar=buscar, tipo=tipo,
        prioridad=prioridad, estado=estado, activa=activa, orden=orden,
    )


@router.patch('/admin/fraude/alertas/{alerta_id}')
def fraude_revisar_alerta(
    alerta_id: int,
    payload: AlertaUpdate,
    admin: Usuario = Depends(get_admin),
    db: Session = Depends(get_db),
):
    row = fraud.revisar_alerta(
        db, alerta_id, estado=payload.estado,
        revisor_id=admin.id, notas=payload.notas,
    )
    if not row:
        raise HTTPException(404, 'Alerta no encontrada.')
    return {'ok': True, 'estado': row.estado}


@router.get('/admin/fraude/ventas-flash')
def fraude_ventas_flash(
    limite: int = Query(100, ge=1, le=500),
    _: Usuario = Depends(get_admin),
    neo4j: Neo4jSession = Depends(get_neo4j),
):
    return fraud.detectar_flash_pagadas(neo4j, limite)


@router.get('/admin/fraude/ventas-flash/resumen')
def fraude_ventas_flash_resumen(
    _: Usuario = Depends(get_admin),
    neo4j: Neo4jSession = Depends(get_neo4j),
):
    return fraud.resumen_flash_pagadas(neo4j)


@router.get('/{producto_ref}')
def listar_resenas(
    producto_ref: str,
    todas: bool = Query(False),
    db: Session = Depends(get_db),
    user: Usuario | None = Depends(get_optional_user),
):
    if todas:
        roles = {rol.nombre for rol in user.roles} if user else set()
        if 'administrador' not in roles:
            raise HTTPException(403, 'Solo un administrador puede consultar reseñas no públicas.')
    user_id = user.id if user else None
    resenas = mysql_svc.listar(
        db, producto_ref=producto_ref, solo_publicas=not todas, usuario_id=user_id,
    )
    resumen = mysql_svc.resumen(db, producto_ref)
    return {"resumen": resumen, "resenas": resenas}
