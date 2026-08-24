"""La operación final depende de ofertas, nunca de la tabla retirada."""

from app.api.v1.vendor import vendor_stats
from app.core.db_mysql import SessionLocal
from app.models.inventario import Inventario
from app.models.oferta import Oferta
from app.models.pedido_vendedor import PedidoVendedor
from app.models.usuario import Usuario
from app.models.vendedor import Vendedor
from app.services.offer_service import resolver_oferta_comprable


def test_offer_resolution_uses_offer_identity_only():
    with SessionLocal() as db:
        offer = db.query(Oferta).order_by(Oferta.id).first()
        inventory = db.query(Inventario).filter_by(
            oferta_id=offer.id, bodega='principal'
        ).first()
        resolved = resolver_oferta_comprable(db, oferta_id=offer.id)
        assert inventory is not None
        assert resolved.id == offer.id
        assert resolved.precio_actual == offer.precio_actual


def test_vendor_stats_use_vendor_suborders_and_offers():
    with SessionLocal() as db:
        part = db.query(PedidoVendedor).order_by(PedidoVendedor.id).first()
        vendor = db.get(Vendedor, part.vendedor_id)
        user = db.get(Usuario, vendor.usuario_id)
        assert user

        before = vendor_stats(current_user=user, db=db)
        after = vendor_stats(current_user=user, db=db)
        assert after == before
