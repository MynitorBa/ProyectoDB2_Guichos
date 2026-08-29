"""Carga escenarios repetibles para probar el historial temporal de ofertas.

No elimina datos existentes. La etiqueta ``DEMO-HISTORIAL`` permite detectar
una ejecución anterior y evita duplicar las ofertas o sus intervalos.
"""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.db_mysql import SessionLocal
from app.models.inventario import Inventario, InventarioSaldoHistorial
from app.models.oferta import Oferta, OfertaEstadoHistorial, OfertaPrecioHistorial
from app.models.usuario import Usuario
from app.models.vendedor import Vendedor


MARKER = "[DEMO-HISTORIAL]"
GT_TZ = timezone(timedelta(hours=-6))


def gt_to_utc_naive(day, hour: int, minute: int = 0) -> datetime:
    local = datetime.combine(day, time(hour, minute), tzinfo=GT_TZ)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def close_open_price(db, offer_id: int, at: datetime) -> None:
    current = db.query(OfertaPrecioHistorial).filter_by(
        oferta_id=offer_id, vigente_hasta=None
    ).one()
    current.vigente_hasta = at


def add_price_series(db, offer: Oferta, admin_id: int, values) -> None:
    for index, (at, value, label) in enumerate(values):
        until = values[index + 1][0] if index + 1 < len(values) else None
        db.add(OfertaPrecioHistorial(
            oferta_id=offer.id,
            precio=Decimal(value),
            moneda="GTQ",
            vigente_desde=at,
            vigente_hasta=until,
            cambiado_por=admin_id,
            motivo=f"{MARKER} {label}",
        ))
    offer.precio_actual = Decimal(values[-1][1])
    offer.version += len(values)
    offer.fecha_actualizacion = values[-1][0]


def close_open_stock(db, inventory_id: int, at: datetime) -> None:
    current = db.query(InventarioSaldoHistorial).filter_by(
        inventario_id=inventory_id, vigente_hasta=None
    ).one()
    current.vigente_hasta = at


def add_stock_series(db, inventory: Inventario, admin_id: int, values) -> None:
    for index, (at, available, reserved, label) in enumerate(values):
        until = values[index + 1][0] if index + 1 < len(values) else None
        db.add(InventarioSaldoHistorial(
            inventario_id=inventory.id,
            cantidad_disponible=available,
            cantidad_reservada=reserved,
            vigente_desde=at,
            vigente_hasta=until,
            cambiado_por=admin_id,
            motivo=f"{MARKER} {label}",
        ))
    inventory.cantidad_disponible = values[-1][1]
    inventory.cantidad_reservada = values[-1][2]
    inventory.fecha_actualizacion = values[-1][0]


def add_state_series(db, offer: Oferta, admin_id: int, values) -> None:
    for index, (at, state, label) in enumerate(values):
        until = values[index + 1][0] if index + 1 < len(values) else None
        db.add(OfertaEstadoHistorial(
            oferta_id=offer.id,
            vendedor_id=offer.vendedor_id,
            sku=offer.sku,
            estado=state,
            vigente_desde=at,
            vigente_hasta=until,
            cambiado_por=admin_id,
            motivo=f"{MARKER} {label}",
        ))
    offer.estado = values[-1][1]


def seed_existing_offer(db, *, offer_id: int, admin_id: int, days,
                        prices, stocks, states=None) -> Oferta:
    offer = db.get(Oferta, offer_id)
    if not offer:
        raise RuntimeError(f"No existe la oferta base {offer_id}.")
    inventory = db.query(Inventario).filter_by(
        oferta_id=offer.id, bodega="principal"
    ).one()
    first = gt_to_utc_naive(days[0], 10)
    close_open_price(db, offer.id, first)
    close_open_stock(db, inventory.id, first)
    add_price_series(db, offer, admin_id, prices)
    add_stock_series(db, inventory, admin_id, stocks)

    if states:
        current = db.query(OfertaEstadoHistorial).filter_by(
            oferta_id=offer.id, vigente_hasta=None
        ).one()
        current.vigente_hasta = states[0][0]
        add_state_series(db, offer, admin_id, states)
    return offer


def create_demo_offer(db, *, producto_ref: str, vendor_id: int, sku: str,
                      admin_id: int, created_at: datetime, prices, stocks,
                      states) -> Oferta:
    variant_id = db.query(Oferta.producto_variante_id).filter_by(
        producto_ref=producto_ref
    ).limit(1).scalar()
    if not variant_id:
        raise RuntimeError(f'El producto {producto_ref} no tiene variante registrada.')
    offer = Oferta(
        producto_ref=producto_ref,
        producto_variante_id=variant_id,
        vendedor_id=vendor_id,
        sku=sku,
        precio_actual=Decimal(prices[-1][1]),
        moneda="GTQ",
        estado=states[-1][1],
        version=len(prices),
        fecha_creacion=created_at,
        fecha_actualizacion=prices[-1][0],
    )
    db.add(offer)
    db.flush()
    inventory = Inventario(
        oferta_id=offer.id,
        cantidad_disponible=stocks[-1][1],
        cantidad_reservada=stocks[-1][2],
        punto_reorden=5,
        bodega="principal",
        fecha_actualizacion=stocks[-1][0],
    )
    db.add(inventory)
    db.flush()
    add_price_series(db, offer, admin_id, prices)
    add_stock_series(db, inventory, admin_id, stocks)
    add_state_series(db, offer, admin_id, states)
    return offer


def main() -> int:
    db = SessionLocal()
    try:
        existing = db.query(OfertaPrecioHistorial).filter(
            OfertaPrecioHistorial.motivo.like(f"{MARKER}%")
        ).count()
        if existing:
            print(f"Datos demo ya instalados ({existing} intervalos de precio); no se duplicaron.")
            return 0

        admin = db.query(Usuario).filter_by(email="admin@tiendaya.gt").one()
        vendors = {row.id: row for row in db.query(Vendedor).all()}
        required_vendors = {1, 3, 4, 5}
        if not required_vendors.issubset(vendors):
            raise RuntimeError("Faltan vendedores del conjunto inicial requerido.")

        today = datetime.now(timezone.utc).astimezone(GT_TZ).date()
        days = [today - timedelta(days=offset) for offset in range(4, -1, -1)]

        # Laptop Dell: dos líneas de precio comparables y dos cambios el mismo día.
        dell_times = [gt_to_utc_naive(day, 10) for day in days]
        dell_times.insert(3, gt_to_utc_naive(days[2], 18, 30))
        dell = seed_existing_offer(
            db, offer_id=1, admin_id=admin.id, days=days,
            prices=[
                (dell_times[0], "4899.00", "Precio normal"),
                (dell_times[1], "4799.00", "Promoción de fin de semana"),
                (dell_times[2], "4699.00", "Primer cambio del día"),
                (dell_times[3], "4599.00", "Último cambio del mismo día"),
                (dell_times[4], "4649.00", "Ajuste posterior"),
                (dell_times[5], "4499.00", "Precio vigente"),
            ],
            stocks=[
                (gt_to_utc_naive(days[0], 10), 15, 0, "Saldo inicial demo"),
                (gt_to_utc_naive(days[1], 16), 12, 1, "Ventas y reserva"),
                (gt_to_utc_naive(days[3], 11), 8, 0, "Ventas confirmadas"),
                (gt_to_utc_naive(days[4], 9), 20, 0, "Reabastecimiento"),
            ],
        )
        dell_alt_prices = [
            (gt_to_utc_naive(days[0], 11), "4999.00", "Oferta publicada"),
            (gt_to_utc_naive(days[1], 15), "4749.00", "Promoción"),
            (gt_to_utc_naive(days[2], 12), "4549.00", "Competencia de precio"),
            (gt_to_utc_naive(days[3], 17), "4699.00", "Fin de promoción"),
            (gt_to_utc_naive(days[4], 8), "4399.00", "Precio vigente"),
        ]
        dell_alt = create_demo_offer(
            db, producto_ref=dell.producto_ref, vendor_id=3,
            sku="HIST-DELL-HOGAR", admin_id=admin.id,
            created_at=dell_alt_prices[0][0], prices=dell_alt_prices,
            stocks=[
                (gt_to_utc_naive(days[0], 11), 9, 0, "Saldo inicial demo"),
                (gt_to_utc_naive(days[2], 13), 5, 1, "Ventas y reserva"),
                (gt_to_utc_naive(days[4], 8), 14, 0, "Reabastecimiento"),
            ],
            states=[(gt_to_utc_naive(days[0], 11), "activa", "Oferta publicada")],
        )

        # Colchoneta: reconstrucción de disponibilidad, inventario y pausa temporal.
        yoga = seed_existing_offer(
            db, offer_id=41, admin_id=admin.id, days=days,
            prices=[
                (gt_to_utc_naive(days[0], 10), "199.00", "Precio normal"),
                (gt_to_utc_naive(days[1], 10), "179.00", "Promoción"),
                (gt_to_utc_naive(days[3], 10), "189.00", "Ajuste"),
                (gt_to_utc_naive(days[4], 10), "169.00", "Precio vigente"),
            ],
            stocks=[
                (gt_to_utc_naive(days[0], 10), 55, 0, "Saldo inicial demo"),
                (gt_to_utc_naive(days[1], 14), 30, 4, "Reservas"),
                (gt_to_utc_naive(days[2], 17), 0, 0, "Agotado"),
                (gt_to_utc_naive(days[4], 9), 40, 0, "Reabastecimiento"),
            ],
            states=[
                (gt_to_utc_naive(days[0], 10), "activa", "Estado inicial demo"),
                (gt_to_utc_naive(days[2], 17), "pausada", "Pausa por falta de stock"),
                (gt_to_utc_naive(days[4], 9), "activa", "Reactivada tras reabastecer"),
            ],
        )

        # Libro: segunda oferta para comparar vendedores e incluir una pausa histórica.
        book = db.get(Oferta, 38)
        book_alt_prices = [
            (gt_to_utc_naive(days[0], 9), "109.00", "Oferta publicada"),
            (gt_to_utc_naive(days[1], 13), "104.00", "Promoción"),
            (gt_to_utc_naive(days[2], 11), "96.00", "Primer cambio del día"),
            (gt_to_utc_naive(days[2], 20), "92.00", "Último cambio del mismo día"),
            (gt_to_utc_naive(days[4], 9), "95.00", "Precio vigente"),
        ]
        book_alt = create_demo_offer(
            db, producto_ref=book.producto_ref, vendor_id=5,
            sku="HIST-BABILONIA-SPORT", admin_id=admin.id,
            created_at=book_alt_prices[0][0], prices=book_alt_prices,
            stocks=[
                (gt_to_utc_naive(days[0], 9), 25, 0, "Saldo inicial demo"),
                (gt_to_utc_naive(days[2], 16), 10, 2, "Ventas y reservas"),
                (gt_to_utc_naive(days[3], 12), 10, 0, "Reservas liberadas"),
                (gt_to_utc_naive(days[4], 9), 35, 0, "Reabastecimiento"),
            ],
            states=[
                (gt_to_utc_naive(days[0], 9), "activa", "Oferta publicada"),
                (gt_to_utc_naive(days[3], 8), "pausada", "Pausa comercial"),
                (gt_to_utc_naive(days[4], 9), "activa", "Oferta reactivada"),
            ],
        )

        db.commit()
        print("Carga de demostración completada.")
        print(f"Rango Guatemala: {days[0]} a {days[-1]}")
        print(f"Laptop Dell Inspiron 15: ofertas {dell.id} y {dell_alt.id}")
        print(f"Colchoneta yoga 6mm: oferta {yoga.id}")
        print(f"El hombre más rico de Babilonia: ofertas {book.id} y {book_alt.id}")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
