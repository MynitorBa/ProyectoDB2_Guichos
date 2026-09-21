"""Crea ventas históricas demostrativas y reconstruye Cassandra.

Es opt-in, idempotente por semana y conserva MySQL como fuente de verdad. No
inserta filas falsas directamente en Cassandra: crea pedidos pagados completos
en MySQL y después ejecuta el mismo backfill usado por producción.
"""

import argparse
import sys
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bson import ObjectId

from app.core.db_cassandra import close_cassandra, get_cassandra_session
from app.core.db_mongo import get_mongo_db
from app.core.db_mysql import SessionLocal
from app.models.direccion import Direccion
from app.models.oferta import Oferta
from app.models.pago import MetodoPago, Pago
from app.models.pedido import Pedido, PedidoLinea
from app.models.pedido_vendedor import PedidoDireccion, PedidoVendedor
from app.models.usuario import Usuario
from app.models.vendedor import Vendedor
from app.services.analytics_service import current_week_start, rebuild_all


MARKER = '[DEMO-CASSANDRA]'
GT_TZ = timezone(timedelta(hours=-6))


def utc_demo_time(week_start, offset: int) -> datetime:
    local = datetime.combine(week_start + timedelta(days=2), time(10 + offset), tzinfo=GT_TZ)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def add_address_snapshot(db, order_id: int, buyer: Usuario, address: Direccion) -> None:
    if db.get(PedidoDireccion, order_id):
        return
    db.add(PedidoDireccion(
        pedido_id=order_id,
        receptor_nombre=f'{buyer.nombre} {buyer.apellido}'.strip(),
        receptor_telefono=buyer.telefono,
        pais=address.pais,
        departamento=address.departamento,
        municipio=address.municipio,
        linea1=address.linea1,
        linea2=address.linea2,
        codigo_postal=address.codigo_postal,
    ))


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Genera cinco semanas demostrativas para los dashboards Cassandra.'
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--weeks', type=int, default=5, choices=range(1, 13))
    args = parser.parse_args()
    mongo = get_mongo_db()

    with SessionLocal() as db:
        buyer = db.query(Usuario).filter_by(email='comprador1@gmail.com').first()
        if not buyer:
            raise RuntimeError('No existe comprador1@gmail.com; ejecuta primero el setup normal.')
        address = db.query(Direccion).filter_by(usuario_id=buyer.id, activa=True).first()
        payment_method = db.query(MetodoPago).filter_by(activo=True).first()
        offers = db.query(Oferta).filter(Oferta.estado == 'activa').order_by(
            Oferta.vendedor_id, Oferta.id
        ).all()
        if not address or not payment_method or len(offers) < 6:
            raise RuntimeError('Faltan dirección, método de pago u ofertas activas del seed normal.')

        product_ids = [ObjectId(o.producto_ref) for o in offers if ObjectId.is_valid(o.producto_ref)]
        product_names = {
            str(row['_id']): row.get('nombre')
            for row in mongo.productos.find({'_id': {'$in': product_ids}}, {'nombre': 1})
        }
        vendors = {row.id: row for row in db.query(Vendedor).all()}
        current = current_week_start()
        plans = []
        for week_offset in range(args.weeks):
            week = current - timedelta(days=7 * week_offset)
            marker = f'{MARKER} {week.isoformat()}'
            exists = db.query(Pedido.id).filter(Pedido.notas == marker).first()
            # Rota seis ofertas: genera actividad, caídas a cero y datos de
            # distintos vendedores sin llenar artificialmente todo el catálogo.
            selected = [
                offer for index, offer in enumerate(offers)
                if (index + week_offset) % 4 == 0
            ][:6]
            plans.append((week, marker, exists is not None, selected))

        for week, marker, exists, selected in plans:
            print(
                f'{week}: {"ya existe" if exists else "crear"} '
                f'pedido con {len(selected)} ofertas'
            )
        if args.dry_run:
            print('Dry-run: MySQL y Cassandra no fueron modificados.')
            return 0

        created = 0
        # También repara una ejecución anterior interrumpida después de crear
        # el pedido y antes de reconstruir Cassandra.
        for _week, marker, exists, _selected in plans:
            if exists:
                order_id = db.query(Pedido.id).filter(Pedido.notas == marker).scalar()
                add_address_snapshot(db, order_id, buyer, address)
        for week_offset, (week, marker, exists, selected) in enumerate(plans):
            if exists or not selected:
                continue
            quantities = {offer.id: 1 + ((index + week_offset) % 3) for index, offer in enumerate(selected)}
            subtotal = sum(
                (offer.precio_actual * quantities[offer.id] for offer in selected),
                Decimal('0.00'),
            )
            moment = utc_demo_time(week, week_offset % 4)
            order = Pedido(
                usuario_id=buyer.id,
                direccion_id=address.id,
                estado='confirmado',
                subtotal=subtotal,
                impuestos=Decimal('0.00'),
                total=subtotal,
                notas=marker,
                fecha_creacion=moment,
                fecha_actualizacion=moment,
            )
            db.add(order)
            db.flush()
            add_address_snapshot(db, order.id, buyer, address)
            by_vendor = defaultdict(list)
            for offer in selected:
                by_vendor[offer.vendedor_id].append(offer)
            parts = {}
            for vendor_id, vendor_offers in by_vendor.items():
                vendor_subtotal = sum(
                    (offer.precio_actual * quantities[offer.id] for offer in vendor_offers),
                    Decimal('0.00'),
                )
                part = PedidoVendedor(
                    pedido_id=order.id,
                    vendedor_id=vendor_id,
                    estado='confirmado',
                    subtotal=vendor_subtotal,
                    costo_envio=Decimal('0.00'),
                    fecha_creacion=moment,
                    fecha_actualizacion=moment,
                )
                db.add(part)
                db.flush()
                parts[vendor_id] = part
            for offer in selected:
                quantity = quantities[offer.id]
                db.add(PedidoLinea(
                    pedido_id=order.id,
                    pedido_vendedor_id=parts[offer.vendedor_id].id,
                    oferta_id=offer.id,
                    producto_ref=offer.producto_ref,
                    sku_snapshot=offer.sku,
                    producto_nombre=product_names.get(offer.producto_ref, offer.sku),
                    vendedor_nombre_snapshot=vendors[offer.vendedor_id].nombre_comercial,
                    precio_unitario=offer.precio_actual,
                    cantidad=quantity,
                    subtotal_linea=offer.precio_actual * quantity,
                ))
            db.add(Pago(
                pedido_id=order.id,
                metodo_pago_id=payment_method.id,
                monto=subtotal,
                estado='aprobado',
                referencia_transaccion=f'DEMO-CASS-{week:%Y%m%d}',
                fecha=moment,
            ))
            created += 1
        db.commit()
        result = rebuild_all(db, get_cassandra_session(), mongo)
        print(f'Pedidos demo creados: {created}')
        print(f'Proyección Cassandra reconstruida: {result}')
        print('Vendedor sugerido: vendedor1@tiendaya.gt / password123')
    close_cassandra()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
