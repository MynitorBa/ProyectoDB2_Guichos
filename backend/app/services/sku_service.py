import secrets

from pymongo.database import Database
from sqlalchemy.orm import Session

from app.models.oferta import Oferta


# Genera SKU único tipo 'ELE-4A3F2B1C' verificando colisiones en MongoDB; falla tras 20 intentos
def generate_product_sku(mongo: Database, prefix: str) -> str:
    """Genera el SKU documental único usado por toda creación de productos."""
    normalized = (prefix or 'GEN')[:3].upper()
    for _ in range(20):
        candidate = f'{normalized}-{secrets.token_hex(4).upper()}'
        if not mongo.productos.find_one({'sku': candidate}, {'_id': 1}):
            return candidate
    raise ValueError('No se pudo generar un SKU único para el producto.')


# El primer candidato incluye color y talla como sufijos cuando aplica; si colisiona, agrega hex aleatorio
def generate_offer_sku(
    db: Session,
    *,
    product_sku: str,
    vendor_id: int,
    variante_color: str = '',
    variante_talla: str = '',
    exclude_offer_id: int | None = None,
) -> str:
    """Genera un SKU comercial sin aceptar identificadores elegidos por usuario."""
    parts = [f'V{vendor_id}']
    if variante_color:
        parts.append(variante_color[:4].upper().replace(' ', ''))
    if variante_talla:
        parts.append(variante_talla[:4].upper().replace(' ', ''))
    suffix = '-' + '-'.join(parts)
    base = (product_sku or 'PRODUCTO')[:50 - len(suffix)]
    candidates = [f'{base}{suffix}']
    candidates.extend(
        f'{base[:41]}-{secrets.token_hex(4).upper()}' for _ in range(20)
    )
    for candidate in candidates:
        query = db.query(Oferta).filter(
            Oferta.vendedor_id == vendor_id,
            Oferta.sku == candidate,
        )
        if exclude_offer_id is not None:
            query = query.filter(Oferta.id != exclude_offer_id)
        if not query.first():
            return candidate
    raise ValueError('No se pudo generar un SKU único para la oferta.')
