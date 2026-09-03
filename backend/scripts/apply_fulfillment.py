"""Migración 17 aditiva con respaldo; no inventa fechas de envíos anteriores."""
import json
import sys
from datetime import datetime
from pathlib import Path
from apply_unique_nombre_tiendaya import connect_mysql
from run_sql_migration import run_sql_file

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.core.db_mysql import SessionLocal
from app.models.pedido import Pedido, PedidoLinea
from app.models.pedido_vendedor import PedidoVendedor
from app.models.pedido_envio import PedidoEnvio, PedidoEnvioLinea
from app.services.fulfillment_service import recalculate


def main():
    connection = connect_mysql()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) n FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='pedido_envio_lineas'")
            installed = bool(cursor.fetchone()['n'])
            if not installed:
                data = {}
                for table in ('pedidos', 'pedido_vendedores', 'pedido_lineas', 'solicitudes_catalogo'):
                    cursor.execute(f'SELECT * FROM {table}')
                    data[table] = cursor.fetchall()
                folder = ROOT / 'backups' / 'fulfillment'
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f'before_17_{datetime.now():%Y%m%d_%H%M%S}.json'
                path.write_text(json.dumps(data, default=str, ensure_ascii=False), encoding='utf-8')
                print(f'Respaldo: {path}')
        if not installed:
            run_sql_file(connection, ROOT / 'database/mysql/17_fulfillment_variant_requests.sql')
        with SessionLocal() as db:
            created = 0
            for part in db.query(PedidoVendedor).filter(PedidoVendedor.estado.in_(['enviado', 'entregado'])).all():
                if db.query(PedidoEnvio).filter_by(pedido_vendedor_id=part.id).first():
                    continue
                shipment = PedidoEnvio(pedido_vendedor_id=part.id, estado=part.estado,
                    legado=True, referencia='Estado anterior a envíos parciales; fechas desconocidas')
                db.add(shipment)
                db.flush()
                for line in db.query(PedidoLinea).filter_by(pedido_vendedor_id=part.id).all():
                    db.add(PedidoEnvioLinea(envio_id=shipment.id, pedido_linea_id=line.id, cantidad=line.cantidad))
                created += 1
            aligned = 0
            for order in db.query(Pedido).with_for_update().all():
                if order.estado in {'cancelado', 'reembolsado'}:
                    # La antigua edición global no propagaba estados terminales.
                    # Conserva envíos registrados y NO vuelve a tocar inventario/pagos.
                    for part in db.query(PedidoVendedor).filter_by(pedido_id=order.id).all():
                        if part.estado != order.estado:
                            part.estado = order.estado
                            aligned += 1
                else:
                    recalculate(db, order)
            db.commit()
        print(f'Migración 17 lista. Envíos heredados registrados: {created}. Estados terminales alineados: {aligned}.')
        return 0
    finally:
        connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
