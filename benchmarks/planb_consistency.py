"""Casos analíticos controlados; SOLO MySQL 3337 y Cassandra 9242.

Inserta pedidos/pagos sintéticos en la copia benchmark, nunca en PRINCIPAL.
No invoca el checkout ni la pasarela. Comprueba la proyección Outbox.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.core.config import settings  # noqa: E402
from app.core.db_cassandra import close_cassandra, get_cassandra_session  # noqa: E402
from app.core.db_mysql import SessionLocal  # noqa: E402
from app.models.outbox import OutboxEvento  # noqa: E402
from app.services.analytics_mysql_backup import MySQLAnalyticsAdapter  # noqa: E402
from app.services.analytics_service import _week_for_row, product_trends  # noqa: E402
from app.services.outbox_service import enqueue_outbox, process_one, project_event  # noqa: E402
from app.services import analytics_service, analytics_mysql_backup  # noqa: E402


def guard():
    if (settings.MYSQL_DB != 'tiendaya_benchmark_20261101' or settings.MYSQL_PORT != 3337
            or settings.CASSANDRA_PORT != 9242 or settings.MONGO_URI.find('29999') < 0):
        raise SystemExit('Solo se permite el benchmark aislado, con Mongo deshabilitado')


def create_paid_order(template_line: int, flash: bool = False) -> tuple[int, int]:
    key = str(uuid.uuid4())
    with SessionLocal() as db:
        template = db.execute(text('''
            SELECT p.usuario_id,p.direccion_id,pl.oferta_id,pl.producto_ref,
                   pl.sku_snapshot,pl.producto_nombre,pl.vendedor_nombre_snapshot,
                   pl.precio_unitario,pl.cantidad,pl.subtotal_linea,pv.vendedor_id,
                   (SELECT metodo_pago_id FROM pagos WHERE pedido_id=p.id LIMIT 1) metodo_pago_id
            FROM pedido_lineas pl JOIN pedidos p ON p.id=pl.pedido_id
            JOIN pedido_vendedores pv ON pv.id=pl.pedido_vendedor_id
            WHERE pl.id=:id
        '''), {'id': template_line}).mappings().one()
        t = dict(template)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db.execute(text('''
            INSERT INTO pedidos (usuario_id,direccion_id,estado,subtotal,impuestos,total,
                                 clave_idempotencia,fecha_creacion,fecha_actualizacion)
            VALUES (:usuario_id,:direccion_id,'confirmado',:subtotal_linea,0,:subtotal_linea,
                    :key,:now,:now)
        '''), {**t, 'key': key, 'now': now})
        order_id = db.execute(text('SELECT LAST_INSERT_ID()')).scalar_one()
        db.execute(text('''
            INSERT INTO pedido_vendedores (pedido_id,vendedor_id,estado,subtotal,costo_envio)
            VALUES (:order_id,:vendedor_id,'confirmado',:subtotal_linea,0)
        '''), {**t, 'order_id': order_id})
        vendor_order_id = db.execute(text('SELECT LAST_INSERT_ID()')).scalar_one()
        db.execute(text('''
            INSERT INTO pedido_lineas (pedido_id,pedido_vendedor_id,oferta_id,producto_ref,
                                       sku_snapshot,producto_nombre,vendedor_nombre_snapshot,
                                       precio_unitario,cantidad,subtotal_linea)
            VALUES (:order_id,:vendor_order_id,:oferta_id,:producto_ref,:sku_snapshot,
                    :producto_nombre,:vendedor_nombre_snapshot,:precio_unitario,:cantidad,:subtotal_linea)
        '''), {**t, 'order_id': order_id, 'vendor_order_id': vendor_order_id})
        line_id = db.execute(text('SELECT LAST_INSERT_ID()')).scalar_one()
        db.execute(text('''
            INSERT INTO pagos (pedido_id,metodo_pago_id,monto,estado,clave_idempotencia,
                               referencia_transaccion,fecha)
            VALUES (:order_id,:metodo_pago_id,:subtotal_linea,'aprobado',:key,:ref,:now)
        '''), {**t, 'order_id': order_id, 'key': key, 'ref': f'BENCH-{order_id}', 'now': now})
        if flash:
            promo = db.execute(text('''
                SELECT pf.id FROM reservas_flash rf JOIN promociones_flash pf
                ON pf.id=rf.promocion_id WHERE rf.pedido_id=303 AND pf.oferta_id=:offer
                AND rf.estado='convertida' LIMIT 1
            '''), {'offer': t['oferta_id']}).scalar_one()
            db.execute(text('''
                INSERT INTO reservas_flash (token,promocion_id,usuario_id,cantidad,
                                            precio_unitario,estado,expira_en,pedido_id)
                VALUES (:token,:promo,:user,:quantity,:price,'convertida',
                        DATE_ADD(UTC_TIMESTAMP(), INTERVAL 5 MINUTE),:order_id)
            '''), {'token': str(uuid.uuid4()), 'promo': promo, 'user': t['usuario_id'],
                   'quantity': t['cantidad'], 'price': t['precio_unitario'], 'order_id': order_id})
        db.commit()
    return order_id, line_id


def enqueue_pair(order_id: int):
    with SessionLocal() as db:
        enqueue_outbox(db, tipo_evento='analytics.pedido_actualizado', agregado_tipo='pedido',
                       agregado_id=order_id, producto_ref=None, payload={'pedido_id': order_id},
                       destinos=('cassandra', 'analitica_mysql'))
        db.commit()


def event_status(order_id: int):
    with SessionLocal() as db:
        return {row.destino: row.estado for row in db.query(OutboxEvento).filter(
            OutboxEvento.agregado_id == str(order_id),
            OutboxEvento.tipo_evento == 'analytics.pedido_actualizado').all()}


def compare(week):
    fields = ('producto_ref', 'unidades', 'ingresos_brutos', 'ingresos_reembolsados',
              'ingresos_netos', 'pedidos', 'ofertas', 'unidades_flash')
    with SessionLocal() as db:
        sources = (product_trends(week, get_cassandra_session(), comparison_weeks=0),
                   product_trends(week, MySQLAnalyticsAdapter(db), comparison_weeks=0))
    normalized = [sorted([{f: row[f] for f in fields} for row in source],
                         key=lambda item: item['producto_ref']) for source in sources]
    if normalized[0] != normalized[1]:
        raise AssertionError({'cassandra': normalized[0], 'mysql': normalized[1]})
    return normalized[0]


def main():
    guard()
    # Las imágenes son decorativas: no abrir conexiones a Mongo PRINCIPAL.
    analytics_service._product_images = lambda mongo, refs: {}
    analytics_mysql_backup._product_images = lambda mongo, refs: {}
    result = {'casos': []}
    normal_order, normal_line = create_paid_order(1)
    flash_order, flash_line = create_paid_order(365, flash=True)
    with SessionLocal() as db:
        moment = db.execute(text('SELECT fecha_creacion FROM pedidos WHERE id=:id'),
                            {'id': normal_order}).scalar_one()
    week = _week_for_row({'fecha_hora': moment})
    for kind, order in [('compra_aprobada', normal_order), ('compra_flash', flash_order)]:
        enqueue_pair(order)
        started = time.perf_counter()
        assert process_one('analitica_mysql') and process_one('cassandra')
        rows = compare(week)
        assert event_status(order) == {'cassandra': 'procesado', 'analitica_mysql': 'procesado'}
        if kind == 'compra_flash':
            assert any(row['unidades_flash'] >= 1 for row in rows)
        result['casos'].append({'caso': kind, 'pedido_aislado': order,
                               'proyeccion_ms': round((time.perf_counter()-started)*1000, 2),
                               'filas': len(rows), 'igual': True})

    with SessionLocal() as db:
        db.execute(text("UPDATE pedidos SET estado='reembolsado' WHERE id=:id"), {'id': normal_order})
        db.execute(text("UPDATE pagos SET estado='reembolsado' WHERE pedido_id=:id"), {'id': normal_order})
        db.commit()
    enqueue_pair(normal_order)
    assert process_one('analitica_mysql') and process_one('cassandra')
    rows = compare(week)
    assert any(row['ingresos_reembolsados'] > 0 for row in rows)
    result['casos'].append({'caso': 'reembolso', 'igual': True})

    before_replay = compare(week)
    with SessionLocal() as db:
        event = db.query(OutboxEvento).filter(OutboxEvento.agregado_id == str(flash_order),
                                             OutboxEvento.destino == 'cassandra').first()
        project_event(event, db)
        project_event(event, db)
        event = db.query(OutboxEvento).filter(OutboxEvento.agregado_id == str(flash_order),
                                             OutboxEvento.destino == 'analitica_mysql').first()
        project_event(event, db)
        project_event(event, db)
    rows = compare(week)
    assert rows == before_replay
    for line_id in (normal_line, flash_line):
        with SessionLocal() as db:
            ref = db.execute(text('SELECT producto_ref FROM pedido_lineas WHERE id=:id'),
                             {'id': line_id}).scalar_one()
        details = get_cassandra_session().execute(
            'SELECT pedido_linea_id FROM ventas_producto_semana WHERE producto_ref=%s AND semana_inicio=%s',
            (ref, week))
        assert sum(row.pedido_linea_id == line_id for row in details) == 1
    result['casos'].append({'caso': 'reprocesamiento_doble', 'igual': True, 'duplicados': 0})

    # Caída solamente del contenedor Cassandra BENCHMARK.
    subprocess.run(['docker', 'stop', 'tiendaya_benchmark_cassandra'], check=True,
                   capture_output=True, text=True)
    offline_order = None
    outage_started = time.perf_counter()
    try:
        offline_order, _ = create_paid_order(1)
        enqueue_pair(offline_order)
        assert process_one('analitica_mysql')
        assert event_status(offline_order)['analitica_mysql'] == 'procesado'
        assert process_one('cassandra')
        assert event_status(offline_order)['cassandra'] == 'error'
        with SessionLocal() as db:
            fallback = product_trends(week, MySQLAnalyticsAdapter(db), comparison_weeks=0)
        assert fallback
        result['casos'].append({'caso': 'cassandra_indisponible', 'respaldo_filas': len(fallback),
                               'mysql_procesado': True, 'cassandra_estado': 'error'})
    finally:
        subprocess.run(['docker', 'start', 'tiendaya_benchmark_cassandra'], check=True,
                       capture_output=True, text=True)
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        status = subprocess.run(['docker', 'inspect', 'tiendaya_benchmark_cassandra',
                                 '--format', '{{.State.Health.Status}}'],
                                capture_output=True, text=True, check=True).stdout.strip()
        if status == 'healthy':
            break
        time.sleep(3)
    else:
        raise RuntimeError('Cassandra benchmark no recuperó salud')
    close_cassandra()
    assert process_one('cassandra')
    assert event_status(offline_order) == {'cassandra': 'procesado', 'analitica_mysql': 'procesado'}
    rows = compare(week)
    result['casos'].append({'caso': 'recuperacion', 'igual': True, 'filas': len(rows),
                           'retraso_total_s': round(time.perf_counter()-outage_started, 2),
                           'estado_outbox': event_status(offline_order)})
    output = Path(__file__).resolve().parent / 'results' / '20261101' / 'consistencia.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
