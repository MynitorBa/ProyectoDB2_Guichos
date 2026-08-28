from numbers import Real

from pymongo.database import Database


class AttributeValidationError(ValueError):
    pass


# Valida y normaliza atributos contra los esquemas de todas las categorías seleccionadas; lanza AttributeValidationError si hay conflicto de tipos o campos faltantes
def validate_category_attributes(
    mongo: Database,
    category_slugs: list[str],
    attributes: dict | None,
) -> dict:
    """Valida atributos contra todos los esquemas de categorías seleccionadas."""
    values = attributes or {}
    schemas = {
        row['categoria_slug']: row
        for row in mongo.categoria_esquemas.find(
            {'categoria_slug': {'$in': category_slugs}},
            {'categoria_slug': 1, 'atributos': 1},
        )
    }
    definitions: dict[str, dict] = {}
    for slug in category_slugs:
        for field in schemas.get(slug, {}).get('atributos', []):
            name = field.get('nombre')
            if not name:
                continue
            previous = definitions.get(name)
            if previous and previous.get('tipo') != field.get('tipo'):
                raise AttributeValidationError(
                    f'El atributo "{name}" tiene tipos incompatibles entre categorías.'
                )
            definitions[name] = field

    unknown = sorted(set(values) - set(definitions))
    if unknown:
        raise AttributeValidationError(
            f'Atributos no válidos para las categorías: {", ".join(unknown)}'
        )

    normalized = {}
    missing = []
    for name, field in definitions.items():
        value = values.get(name)
        empty = value is None or (isinstance(value, str) and not value.strip())
        if empty:
            if field.get('requerido'):
                missing.append(field.get('etiqueta') or name)
            continue
        field_type = field.get('tipo', 'string')
        valid = (
            (field_type == 'string' and isinstance(value, str))
            or (field_type == 'number' and isinstance(value, Real) and not isinstance(value, bool))
            or (field_type == 'boolean' and isinstance(value, bool))
        )
        if not valid:
            raise AttributeValidationError(
                f'El atributo "{field.get("etiqueta") or name}" no es de tipo {field_type}.'
            )
        normalized[name] = value.strip() if isinstance(value, str) else value
    if missing:
        raise AttributeValidationError(
            f'Completa los atributos obligatorios: {", ".join(missing)}'
        )
    return normalized
