"""Detección de fraude en reseñas usando patrones de grafo Neo4j."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timedelta, timezone

from neo4j import Session
from sqlalchemy import func
from sqlalchemy.orm import Session as MySQLSession

from app.core.time import utc_now
from app.models.alerta_fraude import AlertaFraude
from app.models.inventario import Inventario, MovimientoInventario
from app.models.oferta import Oferta
from app.models.pago import Pago
from app.models.pedido import Pedido, PedidoLinea
from app.models.vendedor import Vendedor


def detectar_bombardeo(s: Session, ventana_horas: int = 24, umbral: int = 5) -> list[dict]:
    """Productos con más de `umbral` reseñas en las últimas `ventana_horas` horas."""
    return s.run("""
        MATCH (r:Reseña)-[:SOBRE]->(p:Producto)
        WHERE r.fecha IS NOT NULL
          AND datetime(r.fecha) >= datetime() - duration({hours: $horas})
        WITH p, count(r) AS cnt
        WHERE cnt >= $umbral
        RETURN p.ref AS producto_ref, p.nombre AS producto_nombre, cnt AS total_resenas
        ORDER BY cnt DESC
    """, horas=ventana_horas, umbral=umbral).data()


def detectar_sin_compra(s: Session) -> list[dict]:
    """Reseñas de usuarios que nunca compraron el producto."""
    return s.run("""
        MATCH (u:Usuario)-[:ESCRIBIO]->(r:Reseña)-[:SOBRE]->(p:Producto)
        WHERE r.verificada = false AND r.estado IN ['pendiente', 'aprobada']
        RETURN
            u.id   AS usuario_id,
            u.nombre AS usuario_nombre,
            p.ref  AS producto_ref,
            p.nombre AS producto_nombre,
            r.id   AS resena_id,
            r.calificacion AS calificacion,
            r.fecha AS fecha
        ORDER BY r.fecha DESC
        LIMIT 50
    """).data()


def detectar_reviewer_unico_vendedor(s: Session, min_resenas: int = 3) -> list[dict]:
    """Usuarios que solo reseñan productos de un mismo vendedor (posible patrón coordinado)."""
    return s.run("""
        MATCH (u:Usuario)-[:ESCRIBIO]->(r:Reseña)-[:CALIFICA_A]->(v:Vendedor)
        WITH u, count(DISTINCT v) AS vendedores_distintos, count(r) AS total_resenas
        WHERE total_resenas >= $min_resenas AND vendedores_distintos = 1
        MATCH (u)-[:ESCRIBIO]->(r2:Reseña)-[:CALIFICA_A]->(v2:Vendedor)
        RETURN
            u.id   AS usuario_id,
            u.nombre AS usuario_nombre,
            v2.id  AS vendedor_id,
            v2.nombre AS vendedor_nombre,
            total_resenas,
            vendedores_distintos
        ORDER BY total_resenas DESC
        LIMIT 30
    """, min_resenas=min_resenas).data()


def detectar_cluster_coordinado(s: Session, min_comun: int = 3) -> list[dict]:
    """Pares de usuarios que han reseñado los mismos productos múltiples veces."""
    return s.run("""
        MATCH (u1:Usuario)-[:ESCRIBIO]->(:Reseña)-[:SOBRE]->(p:Producto)<-[:SOBRE]-(:Reseña)<-[:ESCRIBIO]-(u2:Usuario)
        WHERE u1.id < u2.id
        WITH u1, u2, count(DISTINCT p) AS productos_comunes
        WHERE productos_comunes >= $min_comun
        RETURN
            u1.id   AS usuario1_id,
            u1.nombre AS usuario1_nombre,
            u2.id   AS usuario2_id,
            u2.nombre AS usuario2_nombre,
            productos_comunes
        ORDER BY productos_comunes DESC
        LIMIT 20
    """, min_comun=min_comun).data()


def resumen_fraude(s: Session) -> dict:
    """Resumen ejecutivo de señales de fraude activas."""
    bombardeo   = detectar_bombardeo(s)
    sin_compra  = detectar_sin_compra(s)
    unico_vend  = detectar_reviewer_unico_vendedor(s)
    cluster     = detectar_cluster_coordinado(s)
    return {
        "bombardeo":            {"count": len(bombardeo),  "items": bombardeo[:5]},
        "sin_compra_verificada":{"count": len(sin_compra), "items": sin_compra[:5]},
        "reviewer_unico_vendedor": {"count": len(unico_vend), "items": unico_vend[:5]},
        "cluster_coordinado":   {"count": len(cluster),    "items": cluster[:5]},
    }


def detectar_autocompras(s: Session) -> list[dict]:
    """Compras pagadas en las que el comprador gestiona al vendedor receptor."""
    return s.run("""
        MATCH (u:Usuario)-[:GESTIONA]->(v:Vendedor)
        MATCH (u)-[:REALIZO]->(c:Compra)-[:A_VENDEDOR]->(v)
        MATCH (c)-[:DE_PRODUCTO]->(p:Producto)
        WITH u, v, p, c.oferta_id AS oferta_id,
             count(c) AS compras, sum(coalesce(c.cantidad, 0)) AS unidades,
             collect(c.linea_id) AS lineas,
             min(c.fecha) AS primera_fecha, max(c.fecha) AS ultima_fecha
        RETURN u.id AS usuario_id, u.nombre AS usuario_nombre,
               v.id AS vendedor_id, v.nombre AS vendedor_nombre,
               p.ref AS producto_ref, p.nombre AS producto_nombre,
               oferta_id, compras, unidades, lineas, primera_fecha, ultima_fecha
        ORDER BY compras DESC, unidades DESC
    """).data()


def detectar_flash_pagadas(s: Session, limite: int = 100) -> list[dict]:
    """Solo conversiones pagadas; no incluye reservas ni intentos fallidos."""
    return s.run("""
        MATCH (u:Usuario)-[:REALIZO]->(c:Compra)-[:DE_PRODUCTO]->(p:Producto)
        MATCH (c)-[:A_VENDEDOR]->(v:Vendedor)
        WHERE c.promocion_flash_id IS NOT NULL AND c.pagada = true
        RETURN c.promocion_flash_id AS promocion_id,
               c.linea_id AS linea_id, c.pedido_id AS pedido_id,
               u.id AS usuario_id, v.id AS vendedor_id,
               p.ref AS producto_ref, p.nombre AS producto_nombre,
               c.oferta_id AS oferta_id, c.cantidad AS cantidad,
               c.precio_unitario AS precio_unitario, c.fecha AS fecha
        ORDER BY c.fecha DESC
        LIMIT $limite
    """, limite=limite).data()


def resumen_flash_pagadas(s: Session) -> list[dict]:
    """Concentración retrospectiva por promoción; excluye reservas e intentos."""
    return s.run("""
        MATCH (u:Usuario)-[:REALIZO]->(c:Compra)-[:DE_PRODUCTO]->(:Producto)
        WHERE c.promocion_flash_id IS NOT NULL AND c.pagada = true
        WITH c.promocion_flash_id AS promocion_id,
             c.oferta_id AS oferta_id, u.id AS usuario_id,
             sum(coalesce(c.cantidad, 0)) AS unidades_usuario,
             count(c) AS compras_usuario
        WITH promocion_id, collect(DISTINCT oferta_id) AS ofertas,
             count(DISTINCT usuario_id) AS compradores,
             sum(unidades_usuario) AS unidades,
             sum(compras_usuario) AS compras,
             max(unidades_usuario) AS max_unidades_comprador
        RETURN promocion_id, ofertas, compradores, unidades, compras,
               max_unidades_comprador,
               CASE WHEN unidades = 0 THEN 0.0
                    ELSE round(100.0 * max_unidades_comprador / unidades, 2)
               END AS concentracion_max_comprador_pct
        ORDER BY concentracion_max_comprador_pct DESC, promocion_id DESC
    """).data()


def _resenas_ligadas_a_lineas(s: Session, lineas: list[int]) -> list[str]:
    """Reseñas que declaran como respaldo una de las compras señaladas."""
    if not lineas:
        return []
    row = s.run("""
        MATCH (r:Reseña)-[:BASADA_EN]->(c:Compra)
        WHERE c.linea_id IN $lineas
        RETURN collect(DISTINCT r.id) AS resenas
    """, lineas=lineas).single()
    return list((row or {}).get('resenas') or [])


def _fecha_neo(value) -> datetime | None:
    """Normaliza fechas proyectadas por Neo4j al DATETIME UTC usado por MySQL."""
    if value is None:
        return None
    raw = str(value).replace('Z', '+00:00')
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _fingerprint(tipo: str, *parts) -> str:
    raw = json.dumps([tipo, *parts], sort_keys=True, default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _guardar_alerta(db: MySQLSession, *, tipo: str, prioridad: str,
                    motivos: list[str], evidencias: dict,
                    usuario_id: int | None = None,
                    vendedor_id: int | None = None,
                    producto_ref: str | None = None,
                    oferta_id: int | None = None) -> AlertaFraude:
    huella = _fingerprint(tipo, usuario_id, vendedor_id, producto_ref, oferta_id)
    row = db.query(AlertaFraude).filter_by(huella=huella).first()
    if not row:
        row = AlertaFraude(
            huella=huella, tipo=tipo, prioridad=prioridad,
            usuario_id=usuario_id, vendedor_id=vendedor_id,
            producto_ref=producto_ref, oferta_id=oferta_id,
            motivos=motivos, evidencias=evidencias,
        )
        db.add(row)
    else:
        row.prioridad = prioridad
        row.motivos = motivos
        row.evidencias = evidencias
        row.ultima_deteccion = utc_now()
    return row


def recalcular_alertas(db: MySQLSession, neo4j: Session) -> dict:
    """Genera indicios explicables sin bloquear compras ni modificar inventario."""
    self_rows = detectar_autocompras(neo4j)
    self_count = 0
    for signal in self_rows:
        compras = int(signal['compras'])
        unidades = int(signal['unidades'] or 0)
        ventana_inicio = _fecha_neo(signal.get('primera_fecha'))
        ventana_fin = _fecha_neo(signal.get('ultima_fecha'))
        moves = (
            db.query(MovimientoInventario)
            .join(Inventario, Inventario.id == MovimientoInventario.inventario_id)
            .filter(
                Inventario.oferta_id == signal['oferta_id'],
                MovimientoInventario.tipo.in_(['entrada', 'ajuste']),
                MovimientoInventario.cantidad > 0,
            )
        )
        # La correlación es temporal: no basta con que una oferta haya recibido
        # inventario en cualquier momento de su historia.
        if ventana_inicio and ventana_fin:
            moves = moves.filter(
                MovimientoInventario.fecha >= ventana_inicio - timedelta(days=3),
                MovimientoInventario.fecha <= ventana_fin + timedelta(days=3),
            )
        moves = moves.order_by(MovimientoInventario.fecha.desc()).limit(20).all()

        owner_id = (
            db.query(Vendedor.usuario_id)
            .filter(Vendedor.id == signal['vendedor_id'])
            .scalar()
        )
        movimientos_por_dueno = sum(1 for move in moves if move.usuario_id == owner_id)
        total_unidades = int((
            db.query(func.coalesce(func.sum(PedidoLinea.cantidad), 0))
            .join(Pedido, Pedido.id == PedidoLinea.pedido_id)
            .filter(
                PedidoLinea.oferta_id == signal['oferta_id'],
                Pedido.estado.notin_(['cancelado', 'reembolsado']),
                db.query(Pago.id).filter(
                    Pago.pedido_id == Pedido.id,
                    Pago.estado == 'aprobado',
                ).exists(),
            )
            .scalar()
        ) or 0)
        concentracion = round((unidades / total_unidades) * 100, 2) if total_unidades else 0
        resenas_ligadas = _resenas_ligadas_a_lineas(neo4j, signal.get('lineas') or [])
        reasons = ['El comprador es el propietario actual del vendedor receptor.']
        if compras >= 3:
            reasons.append(f'Acumula {compras} autocompras pagadas para la misma oferta.')
        if unidades >= 10:
            reasons.append(f'El volumen autocomprado alcanza {unidades} unidades.')
        if len(moves) >= 3:
            reasons.append(
                f'La oferta tiene {len(moves)} entradas/ajustes positivos cerca de las autocompras.'
            )
        if movimientos_por_dueno:
            reasons.append(
                f'{movimientos_por_dueno} movimientos correlacionados fueron registrados por el propietario.'
            )
        if concentracion >= 50:
            reasons.append(
                f'Las autocompras representan {concentracion}% de las unidades pagadas de la oferta.'
            )
        if resenas_ligadas:
            reasons.append(
                f'{len(resenas_ligadas)} reseñas están respaldadas por las compras señaladas.'
            )
        priority = 'alta' if compras >= 3 and (unidades >= 10 or len(moves) >= 3) else (
            'media' if compras >= 2 or unidades >= 5 else 'informativa'
        )
        _guardar_alerta(
            db, tipo='autocompra', prioridad=priority, motivos=reasons,
            usuario_id=signal['usuario_id'], vendedor_id=signal['vendedor_id'],
            producto_ref=signal['producto_ref'], oferta_id=signal['oferta_id'],
            evidencias={
                **signal,
                'ventana_correlacion_dias': 3,
                'movimientos_positivos': [m.id for m in moves],
                'movimientos_por_propietario': movimientos_por_dueno,
                'unidades_pagadas_oferta': total_unidades,
                'concentracion_autocompra_pct': concentracion,
                'resenas_ligadas': resenas_ligadas,
            },
        )
        self_count += 1

    cutoff = utc_now() - timedelta(days=30)
    inventory_rows = (
        db.query(
            Oferta.id.label('oferta_id'), Oferta.vendedor_id,
            Oferta.producto_ref,
            func.count(MovimientoInventario.id).label('movimientos'),
            func.sum(MovimientoInventario.cantidad).label('unidades'),
        )
        .join(Inventario, Inventario.oferta_id == Oferta.id)
        .join(MovimientoInventario, MovimientoInventario.inventario_id == Inventario.id)
        .filter(
            MovimientoInventario.tipo.in_(['entrada', 'ajuste']),
            MovimientoInventario.cantidad > 0,
            MovimientoInventario.fecha >= cutoff,
        )
        .group_by(Oferta.id, Oferta.vendedor_id, Oferta.producto_ref)
        .having((func.count(MovimientoInventario.id) >= 3) |
                (func.sum(MovimientoInventario.cantidad) >= 25))
        .all()
    )
    inventory_count = 0
    for row in inventory_rows:
        owner_id = db.query(Vendedor.usuario_id).filter(
            Vendedor.id == row.vendedor_id
        ).scalar()
        movements = (
            db.query(MovimientoInventario)
            .join(Inventario, Inventario.id == MovimientoInventario.inventario_id)
            .filter(
                Inventario.oferta_id == row.oferta_id,
                MovimientoInventario.fecha >= cutoff,
            )
            .order_by(MovimientoInventario.fecha, MovimientoInventario.id)
            .all()
        )
        positive = [
            move for move in movements
            if move.tipo in {'entrada', 'ajuste'} and move.cantidad > 0
        ]
        sales = [move for move in movements if move.tipo == 'salida']
        owner_positive = [move for move in positive if move.usuario_id == owner_id]
        manual_adjustments = [move for move in positive if move.tipo == 'ajuste']
        correlated_pairs = []
        for replenishment in positive:
            nearby = next((
                sale for sale in sales
                if abs((sale.fecha - replenishment.fecha).total_seconds()) <= 3 * 86400
            ), None)
            if nearby:
                correlated_pairs.append((nearby.id, replenishment.id))

        # Vender mucho y reponer inventario no basta. Se exige reiteración
        # temporal, ajustes manuales frecuentes o intervención repetida del
        # propio vendedor para abrir un expediente investigable.
        suspicious = (
            len(correlated_pairs) >= 2
            or len(manual_adjustments) >= 3
            or (len(owner_positive) >= 2 and int(row.unidades or 0) >= 25)
        )
        if not suspicious:
            continue
        motivos = [
            f'{row.movimientos} entradas/ajustes positivos en 30 días.',
            f'El aumento acumulado es de {int(row.unidades or 0)} unidades.',
            'La señal requiere revisar respaldo de abastecimiento; no prueba fraude por sí sola.',
        ]
        if correlated_pairs:
            motivos.append(
                f'{len(correlated_pairs)} reposiciones ocurrieron a ±3 días de una salida.'
            )
        if manual_adjustments:
            motivos.append(f'{len(manual_adjustments)} aumentos fueron ajustes manuales.')
        if owner_positive:
            motivos.append(
                f'{len(owner_positive)} aumentos fueron registrados por el propietario del vendedor.'
            )
        _guardar_alerta(
            db, tipo='inventario_atipico',
            prioridad=(
                'media' if len(correlated_pairs) >= 3
                or len(owner_positive) >= 3
                or int(row.unidades or 0) >= 50 else 'baja'
            ),
            motivos=motivos, vendedor_id=row.vendedor_id,
            producto_ref=row.producto_ref, oferta_id=row.oferta_id,
            evidencias={
                'ventana_dias': 30, 'movimientos': row.movimientos,
                'unidades_positivas': int(row.unidades or 0),
                'movimientos_positivos': [move.id for move in positive],
                'ajustes_manuales': [move.id for move in manual_adjustments],
                'movimientos_por_propietario': [move.id for move in owner_positive],
                'pares_salida_reposicion': correlated_pairs,
                'criterio_demo': True,
            },
        )
        inventory_count += 1
    db.commit()
    return {'autocompras': self_count, 'inventario_atipico': inventory_count}


def listar_alertas(db: MySQLSession, estado: str | None = None) -> list[dict]:
    query = db.query(AlertaFraude)
    if estado:
        query = query.filter(AlertaFraude.estado == estado)
    rows = query.order_by(AlertaFraude.ultima_deteccion.desc()).limit(200).all()
    return [{
        'id': row.id, 'tipo': row.tipo, 'prioridad': row.prioridad,
        'estado': row.estado, 'usuario_id': row.usuario_id,
        'vendedor_id': row.vendedor_id, 'producto_ref': row.producto_ref,
        'oferta_id': row.oferta_id, 'motivos': row.motivos,
        'evidencias': row.evidencias,
        'primera_deteccion': row.primera_deteccion.isoformat(),
        'ultima_deteccion': row.ultima_deteccion.isoformat(),
        'notas_revision': row.notas_revision,
    } for row in rows]


def revisar_alerta(db: MySQLSession, alerta_id: int, *, estado: str,
                   revisor_id: int, notas: str | None) -> AlertaFraude | None:
    row = db.get(AlertaFraude, alerta_id)
    if not row:
        return None
    row.estado = estado
    row.revisada_por = revisor_id
    row.notas_revision = notas
    db.commit()
    return row
