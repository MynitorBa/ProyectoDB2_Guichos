"""Verificación de invariantes de consistencia entre componentes.

Cada invariante expresa una propiedad que la estrategia de consistencia del
checkout promete mantener, incluso después de fallas. Se ejecuta antes y
después de cada prueba de falla como evidencia de que el sistema quedó en un
estado correcto (y no solo de que "no se cayó").

Los pedidos de la saga se identifican por ``clave_idempotencia``; los pedidos
semilla anteriores a la Entrega 3 se reportan como nota, no como violación.
"""

from __future__ import annotations

from datetime import timedelta

import httpx
from bson import ObjectId
from pymongo.database import Database
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utc_now
from app.services.offer_service import listar_ofertas_por_referencias, proyeccion_oferta_principal

ESTADOS_VENDIDOS = ('confirmado', 'preparando', 'enviado_parcial', 'enviado', 'entregado_parcial', 'entregado')
MINUTOS_ATASCO = 5
MINUTOS_VERIFICACION = 30
EJEMPLOS = 5


def _resultado(clave: str, titulo: str, violaciones: list, detalle: str, **extra) -> dict:
    return {
        'id': clave,
        'titulo': titulo,
        'ok': not violaciones,
        'violaciones': len(violaciones),
        'ejemplos': violaciones[:EJEMPLOS],
        'detalle': detalle,
        **extra,
    }


def _filas(db: Session, sql: str, **params) -> list[dict]:
    return [dict(r) for r in db.execute(text(sql), params).mappings()]


def inventario_coherente(db: Session) -> dict:
    """I1: el stock nunca es negativo ni hay más reservado que disponible."""
    violaciones = _filas(db, """
        SELECT oferta_id, cantidad_disponible, cantidad_reservada FROM inventario
        WHERE cantidad_disponible < 0 OR cantidad_reservada < 0
           OR cantidad_reservada > cantidad_disponible
    """)
    return _resultado('I1', 'Sin sobreventa: 0 ≤ reservado ≤ disponible', violaciones,
                      'Se revisa cada fila de inventario.')


def reservas_explicadas(db: Session) -> dict:
    """I2: cada unidad reservada pertenece a una promoción vigente o a un pedido pendiente."""
    violaciones = _filas(db, """
        SELECT i.oferta_id, i.cantidad_reservada AS reservado,
               COALESCE(f.flash, 0) AS cupo_flash, COALESCE(p.pendiente, 0) AS pedidos_pendientes
        FROM inventario i
        LEFT JOIN (
            SELECT oferta_id, SUM(unidades_totales - unidades_vendidas) AS flash
            FROM promociones_flash WHERE estado IN ('programada', 'activa') GROUP BY oferta_id
        ) f ON f.oferta_id = i.oferta_id
        LEFT JOIN (
            SELECT pl.oferta_id, SUM(pl.cantidad) AS pendiente
            FROM pedido_lineas pl JOIN pedidos pe ON pe.id = pl.pedido_id
            WHERE pe.estado = 'pendiente' AND pe.clave_idempotencia IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM reservas_flash rf JOIN promociones_flash pf ON pf.id = rf.promocion_id
                              WHERE rf.pedido_id = pe.id AND pf.oferta_id = pl.oferta_id)
            GROUP BY pl.oferta_id
        ) p ON p.oferta_id = i.oferta_id
        WHERE i.bodega = 'principal'
          AND i.cantidad_reservada <> COALESCE(f.flash, 0) + COALESCE(p.pendiente, 0)
    """)
    return _resultado('I2', 'Toda reserva está explicada (flash vigente o pedido pendiente)', violaciones,
                      'reservado = cupo flash restante + unidades de pedidos pendientes.')


def pedidos_vendidos_con_pago(db: Session) -> dict:
    """I3: ningún pedido de la saga está vendido sin pago aprobado (salvo contra entrega)."""
    consulta = """
        SELECT pe.id AS pedido_id, pe.estado, pa.estado AS pago, mp.nombre AS metodo
        FROM pedidos pe
        JOIN pagos pa ON pa.pedido_id = pe.id
        JOIN metodos_pago mp ON mp.id = pa.metodo_pago_id
        WHERE pe.estado IN :vendidos
          AND pa.estado <> 'aprobado'
          AND NOT (LOWER(mp.nombre) LIKE '%%contra entrega%%' AND pa.estado = 'pendiente')
          AND pe.clave_idempotencia IS {}
    """
    params = {'vendidos': ESTADOS_VENDIDOS}
    violaciones = [dict(r) for r in db.execute(text(consulta.format('NOT NULL')), params).mappings()]
    heredados = [dict(r) for r in db.execute(text(consulta.format('NULL')), params).mappings()]
    nota = (f'{len(heredados)} pedido(s) semilla anteriores a la saga tienen esta inconsistencia de origen.'
            if heredados else None)
    return _resultado('I3', 'Ningún pedido vendido sin pago aprobado', violaciones,
                      'Pedidos de la saga en estados vendidos.', nota=nota,
                      heredados=[h['pedido_id'] for h in heredados])


def cancelados_liberan_reserva(db: Session) -> dict:
    """I4: todo pedido cancelado devolvió exactamente lo que reservó."""
    violaciones = _filas(db, """
        SELECT pe.id AS pedido_id,
               SUM(CASE WHEN mi.tipo = 'reserva' THEN mi.cantidad ELSE 0 END) AS reservado,
               SUM(CASE WHEN mi.tipo = 'liberacion' THEN mi.cantidad ELSE 0 END) AS liberado
        FROM pedidos pe JOIN movimientos_inventario mi ON mi.pedido_id = pe.id
        WHERE pe.estado = 'cancelado' AND pe.clave_idempotencia IS NOT NULL
        GROUP BY pe.id
        HAVING reservado <> liberado
    """)
    return _resultado('I4', 'Cada pedido cancelado liberó su reserva', violaciones,
                      'Suma de movimientos de reserva = suma de liberaciones.')


def sin_sagas_atascadas(db: Session) -> dict:
    """I5: no hay pedidos olvidados a medio camino."""
    ahora = utc_now()
    violaciones = _filas(db, """
        SELECT pe.id AS pedido_id, pe.reserva_expira_en, pa.estado AS pago, pe.fecha_creacion
        FROM pedidos pe JOIN pagos pa ON pa.pedido_id = pe.id
        WHERE pe.estado = 'pendiente' AND pe.clave_idempotencia IS NOT NULL
          AND ((pa.estado = 'pendiente' AND pe.reserva_expira_en < :atasco)
               OR (pa.estado = 'en_verificacion' AND pe.fecha_creacion < :verificacion))
    """, atasco=ahora - timedelta(minutes=MINUTOS_ATASCO),
        verificacion=ahora - timedelta(minutes=MINUTOS_VERIFICACION))
    for fila in violaciones:
        for campo in ('reserva_expira_en', 'fecha_creacion'):
            if fila.get(campo):
                fila[campo] = fila[campo].isoformat()
    return _resultado('I5', 'Ninguna saga atascada', violaciones,
                      f'Reserva vencida hace más de {MINUTOS_ATASCO} min o pago en verificación '
                      f'por más de {MINUTOS_VERIFICACION} min.')


def pasarela_coincide(db: Session, claves: set[str] | None = None) -> dict:
    """I6: cada cobro de la pasarela corresponde al estado del pedido en MySQL.

    ``claves`` limita la revisión a ciertos cobros (útil en pruebas).
    """
    try:
        respuesta = httpx.get(f'{settings.PAYMENT_GATEWAY_URL}/cobros', params={'limite': 1000}, timeout=3)
        respuesta.raise_for_status()
        cobros = respuesta.json()
    except httpx.HTTPError as exc:
        return {'id': 'I6', 'titulo': 'La pasarela y MySQL coinciden', 'ok': None, 'violaciones': 0,
                'ejemplos': [], 'detalle': f'No verificable: pasarela no disponible ({exc.__class__.__name__}).'}
    pedidos = {
        r['clave']: r for r in _filas(db, """
            SELECT pe.clave_idempotencia AS clave, pe.id AS pedido_id, pe.estado, pa.estado AS pago
            FROM pedidos pe JOIN pagos pa ON pa.pedido_id = pe.id
            WHERE pe.clave_idempotencia IS NOT NULL
        """)
    }
    esperado = {
        'aprobado': lambda p: p['estado'] in ESTADOS_VENDIDOS
                              or (p['estado'] == 'pendiente' and p['pago'] in ('pendiente', 'en_verificacion')),
        'reembolsado': lambda p: p['pago'] == 'reembolsado',
        'rechazado': lambda p: p['estado'] in ('cancelado', 'pendiente'),
    }
    if claves is not None:
        cobros = [c for c in cobros if c['clave'] in claves]
    violaciones = []
    for cobro in cobros:
        pedido = pedidos.get(cobro['clave'])
        if pedido is None:
            violaciones.append({'clave': cobro['clave'], 'cobro': cobro['estado'], 'pedido': None})
        elif not esperado[cobro['estado']](pedido):
            violaciones.append({'clave': cobro['clave'], 'cobro': cobro['estado'],
                                'pedido_id': pedido['pedido_id'], 'pedido': pedido['estado'], 'pago': pedido['pago']})
    return _resultado('I6', 'Cada cobro de la pasarela coincide con su pedido', violaciones,
                      f'{len(cobros)} cobro(s) revisados: aprobado ⇒ vendido (o en resolución), '
                      'reembolsado ⇒ pago reembolsado, ningún cargo sin pedido.')


def proyecciones_convergen(db: Session, mongo: Database, es=None) -> dict:
    """I7: MongoDB y Elasticsearch reflejan MySQL cuando no hay eventos pendientes."""
    pendientes = {
        (r['destino'], r['producto_ref']) for r in _filas(db, """
            SELECT DISTINCT destino, producto_ref FROM outbox_eventos
            WHERE estado IN ('pendiente', 'procesando', 'error') AND producto_ref IS NOT NULL
        """)
    }
    refs = [str(d['_id']) for d in mongo.productos.find({'estado': 'activo'}, {'_id': 1})]
    ofertas = listar_ofertas_por_referencias(db, refs)
    documentos = {}
    if es is not None:
        try:
            from app.core.config import settings as cfg
            for hit in es.mget(index=cfg.ES_INDEX_ALIAS, ids=refs, source=['stock_total'])['docs']:
                if hit.get('found'):
                    documentos[hit['_id']] = hit['_source']
        except Exception:
            es = None
    violaciones = []
    revisados = 0
    for ref in refs:
        esperado = proyeccion_oferta_principal(db, ref)
        stock = sum(o['stock'] for o in ofertas.get(ref, []))
        if ('mongo', ref) not in pendientes:
            revisados += 1
            doc = mongo.productos.find_one({'_id': ObjectId(ref)}, {'stock': 1, 'oferta_id': 1})
            if doc.get('stock') != esperado['stock'] or doc.get('oferta_id') != esperado['oferta_id']:
                violaciones.append({'producto_ref': ref, 'destino': 'mongo',
                                    'stock': doc.get('stock'), 'esperado': esperado['stock']})
        if es is not None and ('busqueda', ref) not in pendientes:
            indexado = documentos.get(ref)
            if indexado is None or indexado.get('stock_total') != stock:
                violaciones.append({'producto_ref': ref, 'destino': 'busqueda',
                                    'stock': indexado and indexado.get('stock_total'), 'esperado': stock})
    detalle = (f'{revisados} productos sin eventos pendientes comparados con MySQL'
               + ('' if es is not None else '; Elasticsearch no verificable') + '.')
    return _resultado('I7', 'Las proyecciones convergen con MySQL', violaciones, detalle,
                      eventos_pendientes=len(pendientes))


def verificar(db: Session, mongo: Database, es=None) -> dict:
    invariantes = [
        inventario_coherente(db),
        reservas_explicadas(db),
        pedidos_vendidos_con_pago(db),
        cancelados_liberan_reserva(db),
        sin_sagas_atascadas(db),
        pasarela_coincide(db),
        proyecciones_convergen(db, mongo, es),
    ]
    db.commit()
    return {
        'ok': all(i['ok'] is not False for i in invariantes),
        'generado_en': utc_now().isoformat(),
        'invariantes': invariantes,
    }
