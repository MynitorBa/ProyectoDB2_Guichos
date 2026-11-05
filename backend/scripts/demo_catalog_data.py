"""Catálogo sintético determinista para la DEMO. No representa fichas oficiales."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class DemoProduct:
    name: str
    description: str
    attributes: dict
    variant_attributes: dict
    price: Decimal
    stock: int


FAMILIES = (
    ('Computadora portátil', 'Equipo para tareas diarias, oficina y estudio', 4299),
    ('Teléfono inteligente', 'Móvil para fotografía y comunicación diaria', 2199),
    ('Audífonos inalámbricos', 'Audio portátil con estuche de carga', 349),
    ('Camisa de algodón', 'Prenda ligera para uso cotidiano', 129),
    ('Pantalón casual', 'Prenda cómoda para uso diario', 239),
    ('Zapatos deportivos', 'Calzado para caminar y correr', 449),
    ('Cafetera de filtro', 'Prepara café en casa con filtro reutilizable', 499),
    ('Novela de ciencia ficción', 'Historia de exploración espacial', 119),
    ('Balón de entrenamiento', 'Balón resistente para práctica recreativa', 149),
    ('Café tostado', 'Café molido de tueste medio para preparar en casa', 79),
    ('Juego de construcción', 'Piezas modulares para creatividad infantil', 199),
    ('Taladro inalámbrico', 'Herramienta recargable de dos velocidades para reparaciones', 899),
)

STORE_NAMES = ('Tecnología Laurel', 'Moda Arco', 'Casa y Lectura', 'Sabores y Juegos')
STORE_DESCRIPTIONS = (
    'Computadoras, teléfonos y audio para uso cotidiano.',
    'Camisas, pantalones y calzado para vestir y caminar.',
    'Artículos para el hogar, libros y artículos deportivos.',
    'Café, juegos y herramientas para el hogar.',
)
FIRST_NAMES = (
    'Lucía', 'Mateo', 'Elena', 'Daniel', 'Sofía', 'Gabriel', 'Valeria', 'Andrés',
    'Camila', 'Emilio', 'Mariana', 'Julián', 'Isabela', 'Tomás', 'Renata', 'Nicolás',
)
SURNAMES = (
    'Morales', 'Castillo', 'Pineda', 'Vargas', 'López', 'Reyes', 'Méndez', 'Fuentes',
    'Solís', 'Barrera', 'Ramos', 'Paz', 'Cabrera', 'Mejía', 'Luna', 'Aguilar',
)


def demo_person_name(index: int) -> tuple[str, str]:
    if index < 0:
        raise ValueError('El índice de persona debe ser positivo')
    first = FIRST_NAMES[index % len(FIRST_NAMES)]
    family = SURNAMES[(index // 16) % len(SURNAMES)]
    second = SURNAMES[(index // 256 + 5) % len(SURNAMES)]
    return first, f'{family} {second}'


def demo_store_name(index: int) -> str:
    if index < 0:
        raise ValueError('El índice de tienda debe ser positivo')
    return f'{STORE_NAMES[index % len(STORE_NAMES)]} {index // len(STORE_NAMES) + 1:02d}'


def demo_store_description(index: int) -> str:
    if index < 0:
        raise ValueError('El índice de tienda debe ser positivo')
    return STORE_DESCRIPTIONS[index % len(STORE_DESCRIPTIONS)] + ' Tienda sintética.'


def category_for(index: int) -> int:
    """Cada tienda de ocho productos trabaja tres categorías afines."""
    if index < 0:
        raise ValueError('El índice de producto debe ser positivo')
    return ((index // 8) * 3 + index % 3) % len(FAMILIES)


def demo_product(index: int) -> DemoProduct:
    if index < 0:
        raise ValueError('El índice de producto debe ser positivo')
    category = category_for(index)
    series = index // 8
    name, description, base_price = FAMILIES[category]
    colors = ('negro', 'azul', 'gris', 'verde')
    color = colors[series % len(colors)]
    model = f'{index + 1:03d}'
    if category == 0:
        ram = (8, 16, 32)[series % 3]
        attrs = {'procesador': ('Core i5', 'Ryzen 5', 'Ryzen 7')[series % 3],
                 'ram_gb': ram, 'almacenamiento': '512 GB SSD', 'pulgadas': 15.6,
                 'sistema_op': 'Linux', 'color': color}
        variant = {'ram_gb': ram, 'color': color}
        description += f' con procesador {attrs["procesador"]}, {ram} GB de RAM, SSD de 512 GB y pantalla de 15.6 pulgadas.'
    elif category == 1:
        attrs = {'ram_gb': 6 + series % 3 * 2, 'almacenamiento': '128 GB',
                 'camara_mp': 48, 'pulgadas': 6.4, 'sistema_op': 'Android', 'color': color}
        variant = {'almacenamiento': '128 GB', 'color': color}
        description += ' con pantalla de 6.4 pulgadas, cámara de 48 MP y 128 GB de almacenamiento.'
    elif category == 2:
        attrs = {'tipo_audio': 'in-ear', 'conectividad': 'Bluetooth 5.2',
                 'bateria_horas': 24, 'cancelacion_ruido': False, 'color': color}
        variant = {'color': color}
        description += ' con conexión Bluetooth 5.2 y hasta 24 horas de autonomía con estuche.'
    elif category == 3:
        size = ('S', 'M', 'L', 'XL')[series % 4]
        attrs = {'talla': size, 'color': color, 'material': '100% algodón',
                 'genero': 'Unisex', 'corte': 'Regular', 'manga': 'Corta'}
        variant = {'talla': size, 'color': color}
        description += f' de algodón, manga corta y corte regular; talla {size}, color {color}.'
    elif category == 4:
        size = ('28', '30', '32', '34')[series % 4]
        attrs = {'talla': size, 'color': color, 'material': 'Mezclilla',
                 'corte': 'Regular', 'genero': 'Unisex'}
        variant = {'talla': size, 'color': color}
        description += f' de mezclilla y corte regular; cintura {size}, color {color}.'
    elif category == 5:
        size = 38 + series % 7
        attrs = {'talla': size, 'color': color, 'material': 'Tela transpirable',
                 'genero': 'Unisex', 'tipo_suela': 'Goma amortiguada'}
        variant = {'talla': size, 'color': color}
        description += f' con tela transpirable y suela de goma amortiguada; talla EU {size}.'
    elif category == 6:
        attrs = {'material': 'Plástico y acero', 'color': color,
                 'dimensiones': '25 x 20 x 30 cm', 'potencia_w': 800,
                 'incluye': 'Filtro reutilizable'}
        variant = {'color': color}
        description += ' de 1.5 litros, 800 W y filtro reutilizable.'
    elif category == 7:
        base_isbn = f'978999220{index:03d}'
        checksum = (10 - sum(int(digit) * (1 if position % 2 == 0 else 3)
                             for position, digit in enumerate(base_isbn)) % 10) % 10
        attrs = {'autor': f'Autor ficticio {series + 1:03d}',
                 'isbn': f'{base_isbn}{checksum}', 'paginas': 240 + series % 6 * 32,
                 'editorial': 'Editorial Ficticia', 'idioma': 'Español',
                 'genero_literario': 'Ciencia ficción'}
        variant = {'idioma': 'Español'}
        description += f' sobre una misión de descubrimiento. {attrs["autor"]}, {attrs["paginas"]} páginas.'
    elif category == 8:
        attrs = {'deporte': 'Fútbol', 'talla': '5', 'material': 'Poliuretano', 'color': color}
        variant = {'color': color}
        description += ' de fútbol, talla 5, cubierta de poliuretano.'
    elif category == 9:
        attrs = {'peso_g': 340, 'origen': 'Guatemala', 'apto_vegano': True,
                 'sin_gluten': True, 'ingredientes': 'Café tostado molido'}
        variant = {'peso_g': 340}
        description += ' en bolsa de 340 g; café tostado y molido.'
    elif category == 10:
        attrs = {'edad_minima': 6, 'num_piezas': 120, 'material': 'Plástico ABS',
                 'requiere_pilas': False, 'genero': 'Unisex'}
        variant = {'num_piezas': 120}
        description += ' con 120 piezas modulares, sin pilas, para mayores de 6 años.'
    else:
        attrs = {'voltaje': '20 V batería', 'uso': 'Carpintería doméstica',
                 'incluye': 'Batería y cargador', 'garantia_meses': 12}
        variant = {'voltaje': '20 V'}
        description += ' con batería de 20 V, dos velocidades y portabrocas de 13 mm.'
    return DemoProduct(
        name=f'{name} Serie {model} {color}',
        description=description,
        attributes=attrs,
        variant_attributes=variant,
        price=Decimal(base_price + (series % 7) * max(10, base_price // 20)),
        stock=350 if index < 40 else 40 + (index * 17) % 111,
    )
