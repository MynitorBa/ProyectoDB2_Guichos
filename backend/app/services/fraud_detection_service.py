"""Detección de fraude en reseñas usando patrones de grafo Neo4j."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timedelta, timezone

from neo4j import Session
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session as MySQLSession, aliased

from app.core.time import utc_now
from app.models.alerta_fraude import AlertaFraude
from app.models.inventario import Inventario, MovimientoInventario
from app.models.oferta import Oferta
from app.models.pago import Pago
from app.models.pedido import Pedido, PedidoLinea
from app.models.vendedor import Vendedor
from app.models.usuario import Usuario
from app.models.resena import Resena
from app.models.producto_referencia import ProductoReferencia


SEGMENTO_PUBLICO = 'verificadas_publicas'
SEGMENTO_HISTORICO = 'historicas_no_verificadas'


def _filtro_resena(alias: str, segmento: str) -> str:
    if segmento == SEGMENTO_PUBLICO:
        return f'{alias}.verificada = true AND {alias}.estado = \'aprobada\''
    if segmento == SEGMENTO_HISTORICO:
        return f'{alias}.verificada = false'
    raise ValueError(f'Segmento de reseñas inválido: {segmento}')


def detectar_bombardeo(
    s: Session, ventana_horas: int = 24, umbral: int = 5,
    segmento: str = SEGMENTO_PUBLICO,
) -> list[dict]:
    """Productos con más de `umbral` reseñas en las últimas `ventana_horas` horas."""
    filtro = _filtro_resena('r', segmento)
    return s.run(f"""
        MATCH (r:Reseña)-[:SOBRE]->(p:Producto)
        WHERE r.fecha IS NOT NULL
          AND {filtro}
          AND datetime(r.fecha) >= datetime() - duration({{hours: $horas}})
        WITH p, count(r) AS cnt
        WHERE cnt >= $umbral
        RETURN p.ref AS producto_ref, p.nombre AS producto_nombre, cnt AS total_resenas
        ORDER BY cnt DESC
    """, horas=ventana_horas, umbral=umbral).data()


def detectar_sin_compra(s: Session, limite: int = 50) -> list[dict]:
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
        LIMIT $limite
    """, limite=limite).data()


def contar_sin_compra(s: Session) -> int:
    row = s.run("""
        MATCH (:Usuario)-[:ESCRIBIO]->(r:Reseña)-[:SOBRE]->(:Producto)
        WHERE r.verificada = false AND r.estado IN ['pendiente', 'aprobada']
        RETURN count(r) AS total
    """).single()
    return int((row or {}).get('total') or 0)


def listar_sin_compra_mysql(
    db: MySQLSession, *, pagina: int = 1, tamano: int = 20,
    buscar: str | None = None,
) -> dict:
    """F04 autoritativo, con evidencia y motivo durable almacenado en MySQL."""
    query = db.query(Resena, Usuario, ProductoReferencia, Vendedor).join(
        Usuario, Usuario.id == Resena.usuario_id,
    ).join(
        ProductoReferencia, ProductoReferencia.id == Resena.producto_referencia_id,
    ).outerjoin(Vendedor, Vendedor.id == Resena.vendedor_id).filter(
        Resena.verificada_compra.is_(False),
        Resena.estado_moderacion.in_(['pendiente', 'aprobada']),
    )
    if buscar:
        term = f'%{buscar.strip()}%'
        query = query.filter(or_(
            Usuario.nombre.ilike(term), Usuario.apellido.ilike(term),
            Usuario.email.ilike(term), ProductoReferencia.producto_ref.ilike(term),
            Vendedor.nombre_comercial.ilike(term), Resena.public_id.ilike(term),
        ))
    total = query.with_entities(func.count(Resena.id)).scalar() or 0
    rows = query.order_by(Resena.fecha.desc(), Resena.id.desc()).offset(
        (pagina - 1) * tamano,
    ).limit(tamano).all()
    items = [{
        'resena_id': review.public_id,
        'usuario_id': user.id,
        'usuario_nombre': f'{user.nombre} {user.apellido}'.strip(),
        'producto_ref': product.producto_ref,
        'producto_nombre': None,
        'vendedor_id': seller.id if seller else None,
        'vendedor_nombre': seller.nombre_comercial if seller else None,
        'calificacion': review.calificacion,
        'fecha': review.fecha.isoformat(),
        'estado': review.estado_moderacion,
        'verificada': bool(review.verificada_compra),
        'motivo_no_verificada': review.motivo_no_verificada or 'Sin compra elegible vinculada',
        'evidencia_disponible': {
            'pedido_linea_id': review.pedido_linea_id,
            'vendedor_id': review.vendedor_id,
        },
        'evidencia_faltante': 'Pago aprobado y línea elegible que respalden esta reseña.',
    } for review, user, product, seller in rows]
    return {
        'items': items, 'total': int(total), 'pagina': pagina,
        'tamano': tamano,
        'paginas': max(1, (int(total) + tamano - 1) // tamano),
    }


def enriquecer_nombres_producto(s: Session, items: list[dict]) -> None:
    """Completa nombres F04 en una sola consulta a la proyección documental.

    MySQL sigue siendo la autoridad de la reseña y su verificación; Neo4j se
    usa únicamente para presentar el nombre legible del producto en la página
    solicitada, evitando una consulta por fila.
    """
    refs = sorted({item.get('producto_ref') for item in items if item.get('producto_ref')})
    if not refs:
        return
    names = {
        row['ref']: row['nombre']
        for row in s.run("""
            MATCH (p:Producto)
            WHERE p.ref IN $refs
            RETURN p.ref AS ref, p.nombre AS nombre
        """, refs=refs)
    }
    for item in items:
        item['producto_nombre'] = names.get(item.get('producto_ref')) or item.get('producto_ref')


def listar_indicador_paginado(
    s: Session, regla: str, *, pagina: int = 1, tamano: int = 20,
    segmento: str = SEGMENTO_PUBLICO, buscar: str | None = None,
    ventana_horas: int = 24, umbral: int = 5,
    min_resenas: int = 3, min_comun: int = 3,
) -> dict:
    """Consulta paginada F01-F04; Neo4j solo devuelve la página solicitada."""
    offset = (pagina - 1) * tamano
    filtro_busqueda = (buscar or '').strip().lower()
    params = {
        'skip': offset, 'limit': tamano, 'buscar': filtro_busqueda,
        'horas': ventana_horas, 'umbral': umbral,
        'min_resenas': min_resenas, 'min_comun': min_comun,
    }
    if regla == 'bombardeo':
        filtro = _filtro_resena('r', segmento)
        base = f"""
            MATCH (u:Usuario)-[:ESCRIBIO]->(r:Reseña)-[:SOBRE]->(p:Producto)
            WHERE r.fecha IS NOT NULL AND {filtro}
              AND datetime(r.fecha) >= datetime() - duration({{hours: $horas}})
            WITH p, collect({{resena_id:r.id, usuario_id:u.id,
                 usuario_nombre:u.nombre, calificacion:r.calificacion,
                 fecha:r.fecha, verificada:r.verificada, estado:r.estado}}) AS resenas
            WHERE size(resenas) >= $umbral
              AND ($buscar = '' OR toLower(coalesce(p.nombre,'')) CONTAINS $buscar
                   OR toLower(coalesce(p.ref,'')) CONTAINS $buscar)
        """
        projection = "p.ref AS producto_ref, p.nombre AS producto_nombre, size(resenas) AS total_resenas, resenas"
        order = 'total_resenas DESC, producto_ref ASC'
    elif regla == 'sin_compra':
        base = """
            MATCH (u:Usuario)-[:ESCRIBIO]->(r:Reseña)-[:SOBRE]->(p:Producto)
            WHERE r.verificada = false AND r.estado IN ['pendiente', 'aprobada']
              AND ($buscar = '' OR toLower(coalesce(u.nombre,'')) CONTAINS $buscar
                   OR toLower(coalesce(p.nombre,'')) CONTAINS $buscar
                   OR toLower(coalesce(p.ref,'')) CONTAINS $buscar
                   OR toLower(coalesce(r.id,'')) CONTAINS $buscar)
            WITH u, r, p
        """
        projection = "u.id AS usuario_id, u.nombre AS usuario_nombre, p.ref AS producto_ref, p.nombre AS producto_nombre, r.id AS resena_id, r.calificacion AS calificacion, r.fecha AS fecha, r.estado AS estado"
        order = 'fecha DESC, resena_id ASC'
    elif regla == 'reviewer_unico_vendedor':
        filtro = _filtro_resena('r', segmento)
        base = f"""
            MATCH (u:Usuario)-[:ESCRIBIO]->(r:Reseña)-[:CALIFICA_A]->(v:Vendedor)
            MATCH (r)-[:SOBRE]->(p:Producto)
            WHERE {filtro}
            WITH u, collect(DISTINCT v) AS vendedores,
                 collect(DISTINCT {{resena_id:r.id, producto_ref:p.ref,
                    producto_nombre:p.nombre, fecha:r.fecha,
                    verificada:r.verificada}}) AS resenas,
                 count(DISTINCT r) AS total_resenas
            WHERE total_resenas >= $min_resenas AND size(vendedores) = 1
            WITH u, vendedores[0] AS v, resenas, total_resenas
            WHERE $buscar = '' OR toLower(coalesce(u.nombre,'')) CONTAINS $buscar
              OR toLower(coalesce(v.nombre,'')) CONTAINS $buscar
        """
        projection = "u.id AS usuario_id, u.nombre AS usuario_nombre, v.id AS vendedor_id, v.nombre AS vendedor_nombre, total_resenas, resenas"
        order = 'total_resenas DESC, usuario_id ASC'
    elif regla == 'cluster':
        filtro1 = _filtro_resena('r1', segmento)
        filtro2 = _filtro_resena('r2', segmento)
        base = f"""
            MATCH (u1:Usuario)-[:ESCRIBIO]->(r1:Reseña)-[:SOBRE]->(p:Producto)<-[:SOBRE]-(r2:Reseña)<-[:ESCRIBIO]-(u2:Usuario)
            WHERE u1.id < u2.id AND {filtro1} AND {filtro2}
            WITH u1, u2, p, collect(DISTINCT {{
                 resena1_id:r1.id, resena1_fecha:r1.fecha,
                 resena1_verificada:r1.verificada,
                 resena2_id:r2.id, resena2_fecha:r2.fecha,
                 resena2_verificada:r2.verificada}}) AS resenas_compartidas
            WITH u1, u2, collect({{ref:p.ref, nombre:p.nombre,
                 resenas:resenas_compartidas}}) AS productos
            WHERE size(productos) >= $min_comun
              AND ($buscar = '' OR toLower(coalesce(u1.nombre,'')) CONTAINS $buscar
                   OR toLower(coalesce(u2.nombre,'')) CONTAINS $buscar)
        """
        projection = "u1.id AS usuario1_id, u1.nombre AS usuario1_nombre, u2.id AS usuario2_id, u2.nombre AS usuario2_nombre, size(productos) AS productos_comunes, productos"
        order = 'productos_comunes DESC, usuario1_id ASC, usuario2_id ASC'
    else:
        raise ValueError('Regla de fraude desconocida.')
    total_row = s.run(base + " RETURN count(*) AS total", **params).single()
    items = s.run(
        base + f" RETURN {projection} ORDER BY {order} SKIP $skip LIMIT $limit",
        **params,
    ).data()
    total = int((total_row or {}).get('total') or 0)
    return {
        'items': items, 'total': total, 'pagina': pagina, 'tamano': tamano,
        'paginas': max(1, (total + tamano - 1) // tamano),
    }


def detectar_reviewer_unico_vendedor(
    s: Session, min_resenas: int = 3,
    segmento: str = SEGMENTO_PUBLICO,
) -> list[dict]:
    """Usuarios que solo reseñan productos de un mismo vendedor (posible patrón coordinado)."""
    filtro = _filtro_resena('r', segmento)
    return s.run(f"""
        MATCH (u:Usuario)-[:ESCRIBIO]->(r:Reseña)-[:CALIFICA_A]->(v:Vendedor)
        WHERE {filtro}
        WITH u, collect(DISTINCT v) AS vendedores, count(DISTINCT r) AS total_resenas
        WHERE total_resenas >= $min_resenas AND size(vendedores) = 1
        WITH u, vendedores[0] AS v, total_resenas
        RETURN
            u.id   AS usuario_id,
            u.nombre AS usuario_nombre,
            v.id  AS vendedor_id,
            v.nombre AS vendedor_nombre,
            total_resenas,
            1 AS vendedores_distintos
        ORDER BY total_resenas DESC
        LIMIT 30
    """, min_resenas=min_resenas).data()


def detectar_cluster_coordinado(
    s: Session, min_comun: int = 3,
    segmento: str = SEGMENTO_PUBLICO,
) -> list[dict]:
    """Pares de usuarios que han reseñado los mismos productos múltiples veces."""
    filtro1 = _filtro_resena('r1', segmento)
    filtro2 = _filtro_resena('r2', segmento)
    return s.run(f"""
        MATCH (u1:Usuario)-[:ESCRIBIO]->(r1:Reseña)-[:SOBRE]->(p:Producto)<-[:SOBRE]-(r2:Reseña)<-[:ESCRIBIO]-(u2:Usuario)
        WHERE u1.id < u2.id AND {filtro1} AND {filtro2}
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
    def card(rule: str, segment: str = SEGMENTO_PUBLICO) -> dict:
        page = listar_indicador_paginado(
            s, rule, pagina=1, tamano=5, segmento=segment,
        )
        return {'count': page['total'], 'items': page['items']}

    return {
        'bombardeo': card('bombardeo'),
        'bombardeo_historico': card('bombardeo', SEGMENTO_HISTORICO),
        'reviewer_unico_vendedor': card('reviewer_unico_vendedor'),
        'reviewer_unico_vendedor_historico': card(
            'reviewer_unico_vendedor', SEGMENTO_HISTORICO,
        ),
        'cluster_coordinado': card('cluster'),
        'cluster_coordinado_historico': card('cluster', SEGMENTO_HISTORICO),
    }


def detectar_autocompras(
    s: Session, ventana_dias: int = 30, historico: bool = False,
    ahora: datetime | None = None,
) -> list[dict]:
    """Compras pagadas en las que el comprador gestiona al vendedor receptor."""
    ahora = ahora or utc_now()
    desde = ahora - timedelta(days=ventana_dias)
    filtro_fecha = '' if historico else 'AND datetime(c.fecha) >= datetime($desde)'
    return s.run(f"""
        MATCH (u:Usuario)-[:GESTIONA]->(v:Vendedor)
        MATCH (u)-[:REALIZO]->(c:Compra)-[:A_VENDEDOR]->(v)
        MATCH (c)-[:DE_PRODUCTO]->(p:Producto)
        WHERE c.pagada = true {filtro_fecha}
        WITH u, v, p, c.oferta_id AS oferta_id,
             count(c) AS compras, sum(coalesce(c.cantidad, 0)) AS unidades,
             collect(c.linea_id) AS lineas,
             min(c.fecha) AS primera_fecha, max(c.fecha) AS ultima_fecha
        RETURN u.id AS usuario_id, u.nombre AS usuario_nombre,
               v.id AS vendedor_id, v.nombre AS vendedor_nombre,
               p.ref AS producto_ref, p.nombre AS producto_nombre,
               oferta_id, compras, unidades, lineas, primera_fecha, ultima_fecha,
               false AS propiedad_historica_verificada,
               $alcance AS alcance_propiedad
        ORDER BY compras DESC, unidades DESC
    """, desde=desde.isoformat(), alcance=(
        'historial_completo_propietario_actual' if historico
        else f'ultimos_{ventana_dias}_dias_propietario_actual'
    )).data()


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


def _movimiento_evidencia(row: MovimientoInventario) -> dict:
    return {
        'movimiento_id': row.id, 'tipo': row.tipo,
        'cantidad': int(row.cantidad), 'fecha': row.fecha.isoformat(),
        'motivo': row.motivo, 'pedido_id': row.pedido_id,
        'responsable_usuario_id': row.usuario_id,
    }


def correlacionar_ventas_reposiciones(
    ventas: list[MovimientoInventario],
    reposiciones: list[MovimientoInventario],
    *, ventana_dias: int = 3,
) -> list[tuple[int, int]]:
    """Asigna cada venta y reposición como máximo una vez.

    F06 conserva una correlación temporal heurística: no exige igualdad de
    cantidades (esa regla pertenece a F07). Solo acepta reposiciones posteriores
    a una venta pagada ya validada por MySQL.
    """
    disponibles = {venta.id: venta for venta in ventas}
    pares: list[tuple[int, int]] = []
    limite_segundos = ventana_dias * 86400
    for reposicion in sorted(reposiciones, key=lambda row: (row.fecha, row.id)):
        candidatos = [
            venta for venta in disponibles.values()
            if venta.fecha <= reposicion.fecha
            and (reposicion.fecha - venta.fecha).total_seconds() <= limite_segundos
        ]
        if not candidatos:
            continue
        venta = max(candidatos, key=lambda row: (row.fecha, row.id))
        pares.append((venta.id, reposicion.id))
        disponibles.pop(venta.id, None)
    return pares


def correlacionar_cantidades_exactas(
    compras: list, reposiciones: list, *, ventana_dias: int = 30,
) -> dict:
    """Empareja compras y entradas 1:1 por oferta, cantidad y ventana temporal.

    Una entrada con más de una compra candidata se conserva como ambigua y no
    genera una coincidencia confirmada. Esto evita presentar causalidad donde
    MySQL solo demuestra una coincidencia de cantidad y tiempo.
    """
    def value(row, key):
        return row[key] if isinstance(row, dict) else getattr(row, key)

    def optional(row, key):
        if isinstance(row, dict):
            return row.get(key)
        return getattr(row, key, None)

    compras_por_id = {int(value(row, 'linea_id')): row for row in compras}
    movimientos_por_id = {
        int(value(row, 'movimiento_id')): row for row in reposiciones
    }
    candidatos_por_movimiento: dict[int, list[int]] = {}
    movimientos_por_compra: dict[int, list[int]] = {}
    limite = timedelta(days=ventana_dias)
    for mov_id, mov in movimientos_por_id.items():
        fecha_mov = value(mov, 'fecha')
        candidatos = sorted(
            linea_id for linea_id, row in compras_por_id.items()
            if int(value(row, 'oferta_id')) == int(value(mov, 'oferta_id'))
            and int(value(row, 'cantidad')) == int(value(mov, 'cantidad'))
            and value(row, 'fecha') < fecha_mov
            and fecha_mov - value(row, 'fecha') <= limite
        )
        candidatos_por_movimiento[mov_id] = candidatos
        for linea_id in candidatos:
            movimientos_por_compra.setdefault(linea_id, []).append(mov_id)

    pares: list[dict] = []
    ambiguos: list[dict] = []
    for mov in sorted(reposiciones, key=lambda row: (
        value(row, 'fecha'), int(value(row, 'movimiento_id')),
    )):
        mov_id = int(value(mov, 'movimiento_id'))
        fecha_mov = value(mov, 'fecha')
        candidatos = candidatos_por_movimiento[mov_id]
        if len(candidatos) == 1 and len(movimientos_por_compra[candidatos[0]]) == 1:
            linea_id = candidatos[0]
            compra = compras_por_id[linea_id]
            pares.append({
                'linea_id': linea_id,
                'pedido_id': int(value(compra, 'pedido_id')),
                'movimiento_id': mov_id,
                'oferta_id': int(value(mov, 'oferta_id')),
                'cantidad': int(value(mov, 'cantidad')),
                'fecha_compra': value(compra, 'fecha').isoformat(),
                'fecha_reposicion': fecha_mov.isoformat(),
                'dias_transcurridos': round(
                    (fecha_mov - value(compra, 'fecha')).total_seconds() / 86400, 3,
                ),
                'comprador_id': optional(compra, 'comprador_id'),
                'comprador_nombre': optional(compra, 'comprador_nombre'),
                'responsable_movimiento_id': optional(mov, 'usuario_id'),
                'responsable_movimiento_nombre': optional(mov, 'responsable_nombre'),
                'tipo_movimiento': optional(mov, 'tipo'),
                'motivo_movimiento': optional(mov, 'motivo'),
            })
        elif candidatos:
            ambiguos.append({
                'movimiento_id': mov_id,
                'oferta_id': int(value(mov, 'oferta_id')),
                'cantidad': int(value(mov, 'cantidad')),
                'lineas_candidatas': candidatos,
                'movimientos_candidatos': sorted({
                    candidate_mov
                    for linea_id in candidatos
                    for candidate_mov in movimientos_por_compra[linea_id]
                }),
            })
    return {'pares': pares, 'ambiguos': ambiguos}


def detectar_coincidencias_cantidad(
    db: MySQLSession, *, ahora: datetime | None = None, ventana_dias: int = 30,
) -> dict:
    """F07: coincidencias exactas entre compras válidas y reposiciones posteriores."""
    ahora = ahora or utc_now()
    desde_movimientos = ahora - timedelta(days=ventana_dias)
    # Una reposición reciente puede corresponder a una compra de hasta 30 días
    # anterior al comienzo de la ventana de movimientos.
    desde_compras = desde_movimientos - timedelta(days=ventana_dias)
    fecha_pago_aprobado = (
        db.query(func.max(Pago.fecha))
        .filter(Pago.pedido_id == Pedido.id, Pago.estado == 'aprobado')
        .correlate(Pedido)
        .scalar_subquery()
    )
    responsable = aliased(Usuario)
    compras = (
        db.query(
            PedidoLinea.id.label('linea_id'), PedidoLinea.pedido_id,
            PedidoLinea.oferta_id, PedidoLinea.cantidad,
            PedidoLinea.producto_ref,
            Pedido.usuario_id.label('comprador_id'),
            func.concat(Usuario.nombre, ' ', Usuario.apellido).label('comprador_nombre'),
            fecha_pago_aprobado.label('fecha'),
        )
        .join(Pedido, Pedido.id == PedidoLinea.pedido_id)
        .join(Usuario, Usuario.id == Pedido.usuario_id)
        .filter(
            fecha_pago_aprobado >= desde_compras,
            Pedido.estado.in_([
                'confirmado', 'preparando', 'enviado_parcial', 'enviado',
                'entregado_parcial', 'entregado',
            ]),
            db.query(Pago.id).filter(
                Pago.pedido_id == Pedido.id, Pago.estado == 'aprobado',
            ).exists(),
            ~db.query(Pago.id).filter(
                Pago.pedido_id == Pedido.id, Pago.estado == 'reembolsado',
            ).exists(),
        )
        .order_by(Pedido.fecha_creacion, PedidoLinea.id)
        .all()
    )
    movimientos = (
        db.query(
            MovimientoInventario.id.label('movimiento_id'),
            Inventario.oferta_id, MovimientoInventario.cantidad,
            MovimientoInventario.fecha, MovimientoInventario.tipo,
            MovimientoInventario.motivo, MovimientoInventario.usuario_id,
            func.concat(responsable.nombre, ' ', responsable.apellido).label('responsable_nombre'),
        )
        .join(Inventario, Inventario.id == MovimientoInventario.inventario_id)
        .outerjoin(responsable, responsable.id == MovimientoInventario.usuario_id)
        .filter(
            MovimientoInventario.fecha >= desde_movimientos,
            MovimientoInventario.tipo.in_(['entrada', 'ajuste']),
            MovimientoInventario.cantidad > 0,
            MovimientoInventario.pedido_id.is_(None),
        )
        .order_by(MovimientoInventario.fecha, MovimientoInventario.id)
        .all()
    )
    resultado = correlacionar_cantidades_exactas(
        compras, movimientos, ventana_dias=ventana_dias,
    )
    ofertas = {
        row.id: row for row in db.query(Oferta).filter(
            Oferta.id.in_({pair['oferta_id'] for pair in resultado['pares']} or {-1})
        ).all()
    }
    resultado['por_oferta'] = {}
    for pair in resultado['pares']:
        resultado['por_oferta'].setdefault(pair['oferta_id'], []).append(pair)
    resultado['ofertas'] = ofertas
    return resultado


def _ventas_pagadas_validas(
    db: MySQLSession, *, oferta_id: int, desde: datetime,
) -> list[MovimientoInventario]:
    cantidad_lineas = (
        db.query(func.coalesce(func.sum(PedidoLinea.cantidad), 0))
        .filter(
            PedidoLinea.pedido_id == MovimientoInventario.pedido_id,
            PedidoLinea.oferta_id == oferta_id,
        )
        .correlate(MovimientoInventario)
        .scalar_subquery()
    )
    return (
        db.query(MovimientoInventario)
        .join(Inventario, Inventario.id == MovimientoInventario.inventario_id)
        .join(Pedido, Pedido.id == MovimientoInventario.pedido_id)
        .filter(
            Inventario.oferta_id == oferta_id,
            MovimientoInventario.tipo == 'salida',
            MovimientoInventario.fecha >= desde,
            MovimientoInventario.pedido_id.isnot(None),
            MovimientoInventario.cantidad == cantidad_lineas,
            Pedido.estado.in_([
                'confirmado', 'preparando', 'enviado_parcial', 'enviado',
                'entregado_parcial', 'entregado',
            ]),
            db.query(Pago.id).filter(
                Pago.pedido_id == Pedido.id,
                Pago.estado == 'aprobado',
            ).exists(),
        )
        .order_by(MovimientoInventario.fecha, MovimientoInventario.id)
        .all()
    )


def _guardar_alerta(db: MySQLSession, *, tipo: str, prioridad: str,
                    motivos: list[str], evidencias: dict,
                    usuario_id: int | None = None,
                    vendedor_id: int | None = None,
                    producto_ref: str | None = None,
                    oferta_id: int | None = None,
                    ejecucion_id: int | None = None,
                    origen: str | None = None) -> AlertaFraude:
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
    row.activa = True
    row.resuelta_en = None
    if ejecucion_id is not None:
        row.ultima_ejecucion_id = ejecucion_id
    if origen is not None:
        row.origen_ultima_deteccion = origen
    return row


def recalcular_alertas(
    db: MySQLSession, neo4j: Session, *, ventana_autocompra_dias: int = 30,
    ahora: datetime | None = None, commit: bool = True,
    ejecucion_id: int | None = None, origen: str | None = None,
    inactivar_ausentes: bool = False,
) -> dict:
    """Genera indicios explicables sin bloquear compras ni modificar inventario."""
    ahora = ahora or utc_now()
    self_rows = detectar_autocompras(
        neo4j, ventana_dias=ventana_autocompra_dias, ahora=ahora,
    )
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
                MovimientoInventario.pedido_id.is_(None),
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
        reasons = [
            'El comprador coincide con el propietario actual del vendedor receptor.',
            'No existe historial temporal de propiedad; la atribución histórica no está verificada.',
            f'La ejecución analiza una ventana móvil de {ventana_autocompra_dias} días.',
        ]
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
                'movimientos_detalle': [_movimiento_evidencia(m) for m in moves],
                'movimientos_por_propietario': movimientos_por_dueno,
                'unidades_pagadas_oferta': total_unidades,
                'concentracion_autocompra_pct': concentracion,
                'resenas_ligadas': resenas_ligadas,
                'ventana_autocompra_dias': ventana_autocompra_dias,
                'propiedad_historica_verificada': False,
            },
            ejecucion_id=ejecucion_id, origen=origen,
        )
        self_count += 1

    cutoff = ahora - timedelta(days=30)
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
            MovimientoInventario.pedido_id.is_(None),
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
            and move.pedido_id is None
        ]
        sales = _ventas_pagadas_validas(
            db, oferta_id=row.oferta_id, desde=cutoff,
        )
        owner_positive = [move for move in positive if move.usuario_id == owner_id]
        manual_adjustments = [move for move in positive if move.tipo == 'ajuste']
        correlated_pairs = correlacionar_ventas_reposiciones(sales, positive)

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
                f'{len(correlated_pairs)} reposiciones ocurrieron dentro de los 3 días posteriores a una salida.'
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
                'movimientos_detalle': [_movimiento_evidencia(move) for move in positive],
                'ajustes_manuales': [move.id for move in manual_adjustments],
                'movimientos_por_propietario': [move.id for move in owner_positive],
                'pares_salida_reposicion': correlated_pairs,
                'salidas_pagadas_detalle': [_movimiento_evidencia(move) for move in sales],
                'criterio_demo': True,
            },
            ejecucion_id=ejecucion_id, origen=origen,
        )
        inventory_count += 1

    exactos = detectar_coincidencias_cantidad(db, ahora=ahora, ventana_dias=30)
    exact_count = 0
    for oferta_id, pares in exactos['por_oferta'].items():
        oferta = exactos['ofertas'].get(oferta_id)
        if not oferta:
            continue
        ambiguos = [
            row for row in exactos['ambiguos']
            if row['oferta_id'] == oferta_id
        ]
        cantidades = sorted({pair['cantidad'] for pair in pares})
        _guardar_alerta(
            db,
            tipo='coincidencia_cantidad',
            prioridad='baja' if len(pares) >= 2 else 'informativa',
            vendedor_id=oferta.vendedor_id,
            producto_ref=oferta.producto_ref,
            oferta_id=oferta_id,
            motivos=[
                f'{len(pares)} compra(s) pagada(s) tienen una reposición posterior de cantidad exacta.',
                f'Cantidades coincidentes: {", ".join(map(str, cantidades))}.',
                'La relación es una señal temporal 1:1; no demuestra por sí sola una reposición fraudulenta.',
                'Compras canceladas, pendientes, rechazadas o reembolsadas fueron excluidas.',
            ],
            evidencias={
                'regla': 'F07',
                'ventana_dias': 30,
                'pares_confirmados': pares,
                'coincidencias_ambiguas_excluidas': ambiguos,
                'criterio': 'misma oferta, misma cantidad, reposición posterior y máximo 30 días',
                'fuente_autoritativa': 'MySQL',
            },
            ejecucion_id=ejecucion_id,
            origen=origen,
        )
        exact_count += 1
    if inactivar_ausentes and ejecucion_id is not None:
        # Asegura que nuevas alertas y cambios de ultima_ejecucion_id sean
        # visibles antes del UPDATE que cierra las señales ausentes.
        db.flush()
        db.query(AlertaFraude).filter(
            AlertaFraude.tipo.in_([
                'autocompra', 'inventario_atipico', 'coincidencia_cantidad',
            ]),
            AlertaFraude.activa.is_(True),
            (
                AlertaFraude.ultima_ejecucion_id.is_(None)
                | (AlertaFraude.ultima_ejecucion_id != ejecucion_id)
            ),
        ).update({
            AlertaFraude.activa: False,
            AlertaFraude.resuelta_en: ahora,
        }, synchronize_session=False)
    if commit:
        db.commit()
    return {
        'autocompras': self_count,
        'inventario_atipico': inventory_count,
        'coincidencia_cantidad': exact_count,
        'coincidencias_ambiguas_excluidas': len(exactos['ambiguos']),
    }


def listar_alertas(db: MySQLSession, estado: str | None = None) -> list[dict]:
    query = db.query(AlertaFraude)
    if estado:
        query = query.filter(AlertaFraude.estado == estado)
    rows = query.order_by(AlertaFraude.ultima_deteccion.desc()).limit(200).all()
    return [{
        'id': row.id, 'tipo': row.tipo, 'prioridad': row.prioridad,
        'estado': row.estado, 'activa': row.activa,
        'usuario_id': row.usuario_id,
        'vendedor_id': row.vendedor_id, 'producto_ref': row.producto_ref,
        'oferta_id': row.oferta_id, 'motivos': row.motivos,
        'evidencias': row.evidencias,
        'primera_deteccion': row.primera_deteccion.isoformat(),
        'ultima_deteccion': row.ultima_deteccion.isoformat(),
        'resuelta_en': row.resuelta_en.isoformat() if row.resuelta_en else None,
        'ultima_ejecucion_id': row.ultima_ejecucion_id,
        'origen': row.origen_ultima_deteccion,
        'notas_revision': row.notas_revision,
    } for row in rows]


def resumen_alertas_comerciales(db: MySQLSession) -> dict:
    rows = db.query(
        AlertaFraude.tipo, func.count(AlertaFraude.id),
    ).filter(AlertaFraude.activa.is_(True)).group_by(AlertaFraude.tipo).all()
    counts = {tipo: int(total) for tipo, total in rows}
    return {
        tipo: {'count': counts.get(tipo, 0), 'items': []}
        for tipo in ('autocompra', 'inventario_atipico', 'coincidencia_cantidad')
    }


def listar_alertas_paginadas(
    db: MySQLSession, *, pagina: int = 1, tamano: int = 20,
    buscar: str | None = None, tipo: str | None = None,
    prioridad: str | None = None, estado: str | None = None,
    activa: bool | None = None, orden: str = 'fecha_desc',
) -> dict:
    """Expedientes F05-F07 con filtros y orden estable ejecutados en MySQL."""
    query = db.query(AlertaFraude).outerjoin(
        Vendedor, Vendedor.id == AlertaFraude.vendedor_id,
    ).outerjoin(Usuario, Usuario.id == AlertaFraude.usuario_id).outerjoin(
        Oferta, Oferta.id == AlertaFraude.oferta_id,
    )
    if tipo:
        query = query.filter(AlertaFraude.tipo == tipo)
    if prioridad:
        query = query.filter(AlertaFraude.prioridad == prioridad)
    if estado:
        query = query.filter(AlertaFraude.estado == estado)
    if activa is not None:
        query = query.filter(AlertaFraude.activa.is_(activa))
    if buscar:
        term = f'%{buscar.strip()}%'
        oferta_buscada = int(buscar.strip().lstrip('#')) if buscar.strip().lstrip('#').isdigit() else -1
        query = query.filter(or_(
            Vendedor.nombre_comercial.ilike(term),
            Oferta.sku.ilike(term),
            AlertaFraude.oferta_id == oferta_buscada,
            AlertaFraude.producto_ref.ilike(term),
            Usuario.nombre.ilike(term), Usuario.apellido.ilike(term),
            db.query(PedidoLinea.id).filter(
                PedidoLinea.oferta_id == AlertaFraude.oferta_id,
                PedidoLinea.producto_nombre.ilike(term),
            ).exists(),
        ))
    total = query.with_entities(func.count(AlertaFraude.id)).scalar() or 0
    prioridad_orden = case(
        (AlertaFraude.prioridad == 'alta', 4),
        (AlertaFraude.prioridad == 'media', 3),
        (AlertaFraude.prioridad == 'baja', 2),
        else_=1,
    )
    producto_nombre_subquery = (
        db.query(PedidoLinea.producto_nombre)
        .filter(PedidoLinea.oferta_id == AlertaFraude.oferta_id)
        .correlate(AlertaFraude)
        .order_by(PedidoLinea.id.desc()).limit(1).scalar_subquery()
    )
    order_by = (
        [prioridad_orden.desc(), AlertaFraude.ultima_deteccion.desc(), AlertaFraude.id.desc()]
        if orden == 'prioridad_desc'
        else [AlertaFraude.ultima_deteccion.desc(), prioridad_orden.desc(), AlertaFraude.id.desc()]
    )
    rows = query.with_entities(
        AlertaFraude,
        Vendedor.nombre_comercial.label('vendedor_nombre'),
        Usuario.nombre.label('usuario_nombre'),
        Usuario.apellido.label('usuario_apellido'),
        Oferta.sku.label('oferta_sku'),
        producto_nombre_subquery.label('producto_nombre'),
    ).order_by(*order_by).offset((pagina - 1) * tamano).limit(tamano).all()
    items = []
    for result in rows:
        row = result[0]
        items.append({
            'id': row.id, 'tipo': row.tipo, 'prioridad': row.prioridad,
            'estado': row.estado, 'activa': row.activa,
            'usuario_id': row.usuario_id,
            'usuario_nombre': (
                f'{result.usuario_nombre or ""} {result.usuario_apellido or ""}'.strip() or None
            ),
            'vendedor_id': row.vendedor_id,
            'vendedor_nombre': result.vendedor_nombre,
            'producto_ref': row.producto_ref,
            'producto_nombre': result.producto_nombre,
            'oferta_id': row.oferta_id,
            'oferta_sku': result.oferta_sku,
            'motivos': row.motivos, 'evidencias': row.evidencias,
            'primera_deteccion': row.primera_deteccion.isoformat(),
            'ultima_deteccion': row.ultima_deteccion.isoformat(),
            'resuelta_en': row.resuelta_en.isoformat() if row.resuelta_en else None,
            'ultima_ejecucion_id': row.ultima_ejecucion_id,
            'origen': row.origen_ultima_deteccion,
            'notas_revision': row.notas_revision,
        })
    return {
        'items': items, 'total': int(total), 'pagina': pagina,
        'tamano': tamano,
        'paginas': max(1, (int(total) + tamano - 1) // tamano),
    }


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
