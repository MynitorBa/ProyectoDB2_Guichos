-- =============================================================================
-- TiendaYa — Datos de prueba representativos
-- =============================================================================

USE tiendaya;

-- ─── ROLES ───────────────────────────────────────────────────────────────────
INSERT INTO roles (id, nombre, descripcion) VALUES
  (1, 'comprador',      'Puede buscar productos, comprar y escribir reseñas'),
  (2, 'vendedor',       'Puede publicar y gestionar su catálogo de productos'),
  (3, 'administrador',  'Acceso total al sistema');

-- ─── MÉTODOS DE PAGO ─────────────────────────────────────────────────────────
INSERT INTO metodos_pago (id, nombre) VALUES
  (1, 'Tarjeta de crédito'),
  (2, 'Tarjeta de débito'),
  (3, 'Transferencia bancaria'),
  (4, 'Pago contra entrega');

-- ─── USUARIOS (15) ───────────────────────────────────────────────────────────
-- password_hash = bcrypt de "password123" (pre-generado para seed)
INSERT INTO usuarios (id, email, password_hash, nombre, apellido, telefono, estado, email_verificado) VALUES
  (1,  'admin@tiendaya.gt',      '$2b$12$m4eWOlabkSnzoaioHQMc0Oa/pzArcAD.Mn0O1sq2L5DaoYqF7IZru', 'Ana',     'García',    '50212340001', 'activo', 1),
  (2,  'vendedor1@tiendaya.gt',  '$2b$12$m4eWOlabkSnzoaioHQMc0Oa/pzArcAD.Mn0O1sq2L5DaoYqF7IZru', 'Carlos',  'López',     '50212340002', 'activo', 1),
  (3,  'vendedor2@tiendaya.gt',  '$2b$12$m4eWOlabkSnzoaioHQMc0Oa/pzArcAD.Mn0O1sq2L5DaoYqF7IZru', 'María',   'Hernández', '50212340003', 'activo', 1),
  (4,  'vendedor3@tiendaya.gt',  '$2b$12$m4eWOlabkSnzoaioHQMc0Oa/pzArcAD.Mn0O1sq2L5DaoYqF7IZru', 'Jorge',   'Martínez',  '50212340004', 'activo', 1),
  (5,  'vendedor4@tiendaya.gt',  '$2b$12$m4eWOlabkSnzoaioHQMc0Oa/pzArcAD.Mn0O1sq2L5DaoYqF7IZru', 'Sofia',   'Pérez',     '50212340005', 'activo', 1),
  (6,  'vendedor5@tiendaya.gt',  '$2b$12$m4eWOlabkSnzoaioHQMc0Oa/pzArcAD.Mn0O1sq2L5DaoYqF7IZru', 'Luis',    'Ramírez',   '50212340006', 'activo', 1),
  (7,  'comprador1@gmail.com',   '$2b$12$m4eWOlabkSnzoaioHQMc0Oa/pzArcAD.Mn0O1sq2L5DaoYqF7IZru', 'Pedro',   'Rodríguez', '50212340007', 'activo', 1),
  (8,  'comprador2@gmail.com',   '$2b$12$m4eWOlabkSnzoaioHQMc0Oa/pzArcAD.Mn0O1sq2L5DaoYqF7IZru', 'Laura',   'González',  '50212340008', 'activo', 1),
  (9,  'comprador3@gmail.com',   '$2b$12$m4eWOlabkSnzoaioHQMc0Oa/pzArcAD.Mn0O1sq2L5DaoYqF7IZru', 'Roberto', 'Sánchez',   '50212340009', 'activo', 1),
  (10, 'comprador4@gmail.com',   '$2b$12$m4eWOlabkSnzoaioHQMc0Oa/pzArcAD.Mn0O1sq2L5DaoYqF7IZru', 'Carmen',  'Torres',    '50212340010', 'activo', 1),
  (11, 'comprador5@gmail.com',   '$2b$12$m4eWOlabkSnzoaioHQMc0Oa/pzArcAD.Mn0O1sq2L5DaoYqF7IZru', 'Miguel',  'Flores',    '50212340011', 'activo', 1),
  (12, 'comprador6@gmail.com',   '$2b$12$m4eWOlabkSnzoaioHQMc0Oa/pzArcAD.Mn0O1sq2L5DaoYqF7IZru', 'Isabel',  'Díaz',      '50212340012', 'activo', 1),
  (13, 'comprador7@gmail.com',   '$2b$12$m4eWOlabkSnzoaioHQMc0Oa/pzArcAD.Mn0O1sq2L5DaoYqF7IZru', 'Andrés',  'Morales',   '50212340013', 'activo', 1),
  (14, 'comprador8@gmail.com',   '$2b$12$m4eWOlabkSnzoaioHQMc0Oa/pzArcAD.Mn0O1sq2L5DaoYqF7IZru', 'Patricia','Jiménez',   '50212340014', 'activo', 1),
  (15, 'comprador9@gmail.com',   '$2b$12$m4eWOlabkSnzoaioHQMc0Oa/pzArcAD.Mn0O1sq2L5DaoYqF7IZru', 'Fernando','Vargas',    '50212340015', 'activo', 1);

-- ─── ASIGNACIÓN DE ROLES ──────────────────────────────────────────────────────
INSERT INTO usuario_rol (usuario_id, rol_id) VALUES
  (1,  3), -- admin
  (2,  2), (2,  1), -- vendedor1 también puede comprar
  (3,  2), (3,  1),
  (4,  2), (4,  1),
  (5,  2), (5,  1),
  (6,  2), (6,  1),
  (7,  1), (8,  1), (9,  1), (10, 1),
  (11, 1), (12, 1), (13, 1), (14, 1), (15, 1);

-- ─── DIRECCIONES ─────────────────────────────────────────────────────────────
INSERT INTO direcciones (id, usuario_id, tipo, departamento, municipio, linea1, es_predeterminada) VALUES
  (1,  1,  'envio',       'Guatemala',     'Guatemala',    'Av. Reforma 7-62 zona 9',         1),
  (2,  7,  'envio',       'Guatemala',     'Mixco',        'Col. Monte María bloque C-5',     1),
  (3,  7,  'facturacion', 'Guatemala',     'Guatemala',    '6a calle 3-14 zona 1',            0),
  (4,  8,  'envio',       'Sacatepéquez',  'Antigua',      'Calle del Arco 22',               1),
  (5,  9,  'envio',       'Quetzaltenango','Quetzaltenango','5a avenida 12-30 zona 1',        1),
  (6,  10, 'envio',       'Guatemala',     'Villa Nueva',  'Cond. Los Álamos casa 14',        1),
  (7,  11, 'envio',       'Escuintla',     'Escuintla',    '4a calle 6-20 zona 3',            1),
  (8,  12, 'envio',       'Guatemala',     'Guatemala',    'Zona Viva, 16 calle 4-55 z.10',   1),
  (9,  13, 'envio',       'Chiquimula',    'Chiquimula',   '3a avenida 8-16',                 1),
  (10, 14, 'envio',       'Guatemala',     'San Miguel Petapa','Residencial El Sauce 3',      1),
  (11, 15, 'envio',       'Alta Verapaz',  'Cobán',        '1a avenida 9-60 zona 2',          1),
  (12, 2,  'envio',       'Guatemala',     'Guatemala',    'Bulevar Liberación 7-55 z.9',     1),
  (13, 3,  'envio',       'Guatemala',     'Mixco',        'Col. Lomas de Portugal L-42',     1);

-- ─── VENDEDORES (5) ──────────────────────────────────────────────────────────
INSERT INTO vendedores (id, usuario_id, nombre_comercial, nit, estado_verificacion) VALUES
  (1, 2, 'TechZone Guatemala',   '1234567-8', 'verificado'),
  (2, 3, 'ModaExpress GT',       '2345678-9', 'verificado'),
  (3, 4, 'HogarIdeal',          '3456789-0', 'verificado'),
  (4, 5, 'LibroMundo GT',       '4567890-1', 'verificado'),
  (5, 6, 'SportMax Guatemala',  '5678901-2', 'verificado');

-- ─── CATEGORÍAS (8 raíces + subcategorías) ───────────────────────────────────
INSERT INTO categorias (id, categoria_padre_id, nombre, slug, descripcion, activa, orden) VALUES
  (1,  NULL, 'Electrónica',  'electronica',  'Dispositivos y gadgets tecnológicos',    1, 1),
  (2,  NULL, 'Ropa',         'ropa',         'Moda para toda la familia',              1, 2),
  (3,  NULL, 'Hogar',        'hogar',        'Todo para tu casa',                      1, 3),
  (4,  NULL, 'Libros',       'libros',       'Literatura, técnicos y educativos',      1, 4),
  (5,  NULL, 'Deportes',     'deportes',     'Equipamiento y ropa deportiva',          1, 5),
  (6,  NULL, 'Alimentos',    'alimentos',    'Productos alimenticios y gourmet',       1, 6),
  (7,  NULL, 'Juguetes',     'juguetes',     'Para niños de todas las edades',         1, 7),
  (8,  NULL, 'Herramientas', 'herramientas', 'Ferretería y herramientas profesionales',1, 8),
  -- Subcategorías de electrónica
  (9,  1,    'Computadoras', 'computadoras', 'Laptops, desktops y accesorios',         1, 1),
  (10, 1,    'Celulares',    'celulares',    'Smartphones y accesorios móviles',       1, 2),
  (11, 1,    'Audio',        'audio',        'Audífonos, bocinas y equipos de sonido', 1, 3),
  -- Subcategorías de ropa
  (12, 2,    'Camisas',      'camisas',      'Camisas y blusas para hombre y mujer',   1, 1),
  (13, 2,    'Pantalones',   'pantalones',   'Pantalones, jeans y shorts',             1, 2),
  (14, 2,    'Calzado',      'calzado',      'Zapatos, tenis y sandalias',             1, 3);

-- ─── PRODUCTOS (65 productos, atributos diferentes por categoría) ─────────────
-- NOTA: La columna descripcion incluye el "atributo extra" que motiva la migración a MongoDB.
-- Por ejemplo, una laptop necesita procesador/RAM/disco; una camisa necesita talla/color/material.
-- Estos atributos variables se modelan correctamente en MongoDB; aquí en MySQL solo guardamos
-- nombre, precio y categoría porque no hay forma limpia de representarlos en columnas fijas.

INSERT INTO productos (id, sku, nombre, descripcion, precio, categoria_id, vendedor_id, estado) VALUES
-- ── ELECTRÓNICA: Computadoras ─────────────────────────────────────────────────
  (1,  'TECH-LAP-001', 'Laptop Dell Inspiron 15',
   'Intel Core i5-1235U | 8GB RAM | 512GB SSD | 15.6" FHD', 4899.00, 9, 1, 'activo'),
  (2,  'TECH-LAP-002', 'Laptop HP Pavilion 14',
   'AMD Ryzen 5 5500U | 16GB RAM | 256GB SSD | 14" IPS', 4299.00, 9, 1, 'activo'),
  (3,  'TECH-LAP-003', 'MacBook Air M2',
   'Apple M2 | 8GB RAM | 256GB SSD | 13.6" Liquid Retina', 10999.00, 9, 1, 'activo'),
  (4,  'TECH-LAP-004', 'Laptop Lenovo IdeaPad 3',
   'Intel Core i3-1215U | 8GB RAM | 128GB SSD | 15.6" HD', 2899.00, 9, 1, 'activo'),
  (5,  'TECH-LAP-005', 'Laptop ASUS VivoBook 14',
   'Intel Core i7-12650H | 16GB RAM | 1TB SSD | 14" OLED', 6799.00, 9, 1, 'activo'),
-- ── ELECTRÓNICA: Celulares ────────────────────────────────────────────────────
  (6,  'TECH-CEL-001', 'Samsung Galaxy A54',
   '6GB RAM | 128GB | 50MP | 6.4" Super AMOLED | Android 13', 2199.00, 10, 1, 'activo'),
  (7,  'TECH-CEL-002', 'iPhone 14',
   '6GB RAM | 128GB | 12MP | 6.1" Super Retina XDR | iOS 16', 7499.00, 10, 1, 'activo'),
  (8,  'TECH-CEL-003', 'Xiaomi Redmi Note 12',
   '4GB RAM | 128GB | 50MP | 6.67" AMOLED | Android 12', 1299.00, 10, 1, 'activo'),
  (9,  'TECH-CEL-004', 'Motorola Edge 40',
   '8GB RAM | 256GB | 50MP | 6.55" pOLED 144Hz | Android 13', 3499.00, 10, 1, 'activo'),
-- ── ELECTRÓNICA: Audio ────────────────────────────────────────────────────────
  (10, 'TECH-AUD-001', 'Audífonos Sony WH-1000XM5',
   'Cancelación de ruido | 30h batería | Bluetooth 5.2 | Negro', 2799.00, 11, 1, 'activo'),
  (11, 'TECH-AUD-002', 'Bocina JBL Charge 5',
   '40W RMS | 20h batería | Waterproof IP67 | Party Boost', 1499.00, 11, 1, 'activo'),
  (12, 'TECH-AUD-003', 'Airpods Pro 2da generación',
   'ANC adaptativo | Audio espacial | USB-C | Blanco', 2199.00, 11, 1, 'activo'),
-- ── ROPA: Camisas ────────────────────────────────────────────────────────────
  (13, 'ROPA-CAM-001', 'Camisa Oxford azul marino hombre',
   'Talla M | Azul marino | 100% algodón | Corte slim fit', 299.00, 12, 2, 'activo'),
  (14, 'ROPA-CAM-002', 'Camisa cuadros franela',
   'Talla L | Rojo/negro | 85% algodón 15% poliéster | Regular fit', 249.00, 12, 2, 'activo'),
  (15, 'ROPA-CAM-003', 'Blusa floral mujer',
   'Talla S | Multicolor | 100% viscosa | Cuello V | Manga corta', 189.00, 12, 2, 'activo'),
  (16, 'ROPA-CAM-004', 'Polo Lacoste clásico',
   'Talla XL | Blanco | 100% piqué algodón | Logo bordado', 549.00, 12, 2, 'activo'),
  (17, 'ROPA-CAM-005', 'Camisa lino blanca hombre',
   'Talla M | Blanco | 55% lino 45% algodón | Manga larga | Casual', 329.00, 12, 2, 'activo'),
  (18, 'ROPA-CAM-006', 'Blusa seda mujer negra',
   'Talla L | Negro | 90% seda 10% elastano | Cuello alto | Elegante', 419.00, 12, 2, 'activo'),
-- ── ROPA: Pantalones ─────────────────────────────────────────────────────────
  (19, 'ROPA-PAN-001', 'Jeans slim fit azul hombre',
   'Talla 32 | Azul índigo | 98% algodón 2% elastano | Slim fit', 399.00, 13, 2, 'activo'),
  (20, 'ROPA-PAN-002', 'Jean skinny mujer negro',
   'Talla 28 | Negro | 95% algodón 5% elastano | Skinny fit', 349.00, 13, 2, 'activo'),
  (21, 'ROPA-PAN-003', 'Pantalón cargo beige',
   'Talla 34 | Beige | 100% algodón | Corte recto | 6 bolsillos', 449.00, 13, 2, 'activo'),
-- ── ROPA: Calzado ────────────────────────────────────────────────────────────
  (22, 'ROPA-CAL-001', 'Tenis Nike Air Force 1',
   'Talla 42 | Blanco | Cuero sintético | Suela de goma | Unisex', 899.00, 14, 2, 'activo'),
  (23, 'ROPA-CAL-002', 'Zapato formal Oxford negro',
   'Talla 43 | Negro | Cuero genuino | Suela de cuero | Hombre', 749.00, 14, 2, 'activo'),
-- ── HOGAR ─────────────────────────────────────────────────────────────────────
  (24, 'HOGAR-COC-001', 'Licuadora Oster 600W',
   '600W | 1.5L | 3 velocidades | Vaso de vidrio | Negro/Plata', 549.00, 3, 3, 'activo'),
  (25, 'HOGAR-COC-002', 'Cafetera Nespresso Essenza Mini',
   '1310W | 19 bar | Cápsulas Nespresso | 0.6L deposito | Rojo', 1299.00, 3, 3, 'activo'),
  (26, 'HOGAR-COC-003', 'Set de ollas Tramontina 5 piezas',
   'Acero inox 18/10 | Apta inducción | Con tapa de vidrio | 16-24cm', 1499.00, 3, 3, 'activo'),
  (27, 'HOGAR-MUE-001', 'Silla ergonómica de oficina',
   'Respaldo mesh | Altura ajustable | Apoyabrazos 4D | Negro', 2299.00, 3, 3, 'activo'),
  (28, 'HOGAR-MUE-002', 'Escritorio esquinero madera 140cm',
   'MDF con chapa madera | 140x100cm | Con cajón | Nogal', 1799.00, 3, 3, 'activo'),
  (29, 'HOGAR-DEC-001', 'Lámpara de pie LED moderna',
   'LED 12W | 3 tonalidades | Altura ajustable 120-160cm | Blanco', 699.00, 3, 3, 'activo'),
  (30, 'HOGAR-DEC-002', 'Cuadro abstracto canvas 60x90cm',
   'Impresión en canvas | Marco de madera | Colores tierra | Listo para colgar', 349.00, 3, 3, 'activo'),
-- ── LIBROS ────────────────────────────────────────────────────────────────────
  (31, 'LIBRO-FIC-001', 'Cien años de soledad — García Márquez',
   'Autor: Gabriel García Márquez | ISBN: 978-0307474728 | 417 págs | Random House', 189.00, 4, 4, 'activo'),
  (32, 'LIBRO-TEC-001', 'Clean Code — Robert C. Martin',
   'Autor: Robert C. Martin | ISBN: 978-0132350884 | 431 págs | Prentice Hall', 349.00, 4, 4, 'activo'),
  (33, 'LIBRO-TEC-002', 'Designing Data-Intensive Applications',
   'Autor: Martin Kleppmann | ISBN: 978-1449373320 | 616 págs | O\'Reilly', 459.00, 4, 4, 'activo'),
  (34, 'LIBRO-EDU-001', 'Fundamentos de Bases de Datos — Silberschatz',
   'Autor: Abraham Silberschatz | ISBN: 978-0073523323 | 960 págs | McGraw-Hill', 599.00, 4, 4, 'activo'),
  (35, 'LIBRO-FIC-002', 'El nombre del viento — Patrick Rothfuss',
   'Autor: Patrick Rothfuss | ISBN: 978-8401337208 | 896 págs | Ediciones B', 229.00, 4, 4, 'activo'),
  (36, 'LIBRO-TEC-003', 'Python Crash Course — Eric Matthes',
   'Autor: Eric Matthes | ISBN: 978-1593279288 | 544 págs | No Starch Press', 389.00, 4, 4, 'activo'),
  (37, 'LIBRO-FIC-003', 'Harry Potter y la piedra filosofal',
   'Autor: J.K. Rowling | ISBN: 978-8498383638 | 309 págs | Salamandra', 149.00, 4, 4, 'activo'),
  (38, 'LIBRO-AUT-001', 'El hombre más rico de Babilonia',
   'Autor: George S. Clason | ISBN: 978-8497774338 | 172 págs | Obelisco', 99.00, 4, 4, 'activo'),
-- ── DEPORTES ──────────────────────────────────────────────────────────────────
  (39, 'DEP-FUT-001', 'Balón de fútbol Nike Premier League',
   'Talla 5 | Cuero sintético TPU | FIFA Quality | Blanco/azul', 449.00, 5, 5, 'activo'),
  (40, 'DEP-GIM-001', 'Mancuernas hexagonales 10kg par',
   '10kg c/u | Goma antideslizante | Mango cromado | Par', 599.00, 5, 5, 'activo'),
  (41, 'DEP-GIM-002', 'Colchoneta yoga 6mm',
   '183x61cm | 6mm espesor | Antideslizante ambos lados | Con correa | Morado', 199.00, 5, 5, 'activo'),
  (42, 'DEP-NAT-001', 'Gafas de natación Speedo Vanquisher',
   'Lente espejado | Sellado de silicona | UV protection | Unisex', 249.00, 5, 5, 'activo'),
  (43, 'DEP-CIC-001', 'Casco ciclismo MTB Giro Fixture',
   'Talla M/L | 17 ventilas | Ajuste dial | Visera ajustable | Negro mate', 699.00, 5, 5, 'activo'),
  (44, 'DEP-ROP-001', 'Licra deportiva mujer',
   'Talla M | Negro/rosa | 80% poliamida 20% elastano | Alta compresión | Tiro alto', 279.00, 5, 5, 'activo'),
  (45, 'DEP-ROP-002', 'Short deportivo hombre',
   'Talla L | Azul marino | 100% poliéster secado rápido | Bolsillo lateral | 7"', 179.00, 5, 5, 'activo'),
-- ── ALIMENTOS ─────────────────────────────────────────────────────────────────
  (46, 'ALI-CAF-001', 'Café molido artesanal Huehuetenango 500g',
   'Origen: Huehuetenango | Tueste medio | Molido para cafetera de goteo | 500g', 129.00, 6, 3, 'activo'),
  (47, 'ALI-CHO-001', 'Chocolate negro 70% cacao 200g',
   'Cacao: 70% | Sin gluten | Origen: Guatemala | 200g | 6 tablillas', 89.00, 6, 3, 'activo'),
  (48, 'ALI-MIE-001', 'Miel de abeja pura 1kg',
   'Miel cruda sin procesar | 100% natural | Origen: Alta Verapaz | 1kg en tarro', 119.00, 6, 3, 'activo'),
  (49, 'ALI-SAL-001', 'Sal negra del Himalaya 250g',
   'Sal mineral | Sin refinar | Apta para dietas especiales | 250g en frasco', 79.00, 6, 3, 'activo'),
  (50, 'ALI-GRA-001', 'Granola artesanal con frutos secos 400g',
   'Avena | Nueces | Almendras | Sin azúcar añadida | Apto vegano | 400g', 99.00, 6, 3, 'activo'),
-- ── JUGUETES ──────────────────────────────────────────────────────────────────
  (51, 'JUG-ARM-001', 'LEGO Creator 3 en 1 Dragón 31112',
   '126 piezas | Edad 6+ | 3 modelos posibles | Incluye instrucciones', 299.00, 7, 4, 'activo'),
  (52, 'JUG-MAD-001', 'Rompecabezas madera animales 40 piezas',
   '40 piezas | Madera MDF | Pintado con tintas no tóxicas | Edad 3+ | 30x22cm', 149.00, 7, 4, 'activo'),
  (53, 'JUG-ELE-001', 'Dron de juguete RC con cámara',
   'Alcance 50m | Cámara 720p | 15 min de vuelo | 2.4GHz | Con 2 baterías', 599.00, 7, 4, 'activo'),
  (54, 'JUG-MUÑ-001', 'Muñeca articulada 30cm con ropa',
   'Altura 30cm | Articulaciones en hombros y caderas | Con 3 cambios de ropa | Edad 4+', 219.00, 7, 4, 'activo'),
  (55, 'JUG-CAR-001', 'Pista de carreras Hot Wheels 60 piezas',
   '60 piezas de pista | Incluye 2 autos | Looping doble | Edad 5+ | Compat. Hot Wheels', 349.00, 7, 4, 'activo'),
-- ── HERRAMIENTAS ─────────────────────────────────────────────────────────────
  (56, 'HER-TAL-001', 'Taladro percutor DeWalt 750W',
   '750W | 13mm portabrocas | 2 velocidades | 0-3000 RPM | Con maletín', 1299.00, 8, 5, 'activo'),
  (57, 'HER-MED-001', 'Multímetro digital Fluke 115',
   'Medición AC/DC | Resistencia | Continuidad | Diodos | 600V CAT III', 899.00, 8, 5, 'activo'),
  (58, 'HER-SAR-001', 'Sargentos de presión rápida 12" par',
   '12 pulgadas | Apertura máx 305mm | Fuerza 200kg | Bar de acero | Par', 249.00, 8, 5, 'activo'),
  (59, 'HER-MAN-001', 'Set llaves combinadas 12 piezas',
   '6-22mm | Acero cromo vanadio | Pulido espejo | Estuche incluido', 399.00, 8, 5, 'activo'),
  (60, 'HER-NIV-001', 'Nivel láser autonivelante 3 líneas',
   '3 líneas cruzadas | Auto-nivel magnético | Alcance 15m | IP54 | Con trípode', 799.00, 8, 5, 'activo'),
  (61, 'HER-ESM-001', 'Esmeril de banco 200W doble disco',
   '200W | Discos 6" | 2950 RPM | Protectores incluidos | Con lámpara de trabajo', 599.00, 8, 5, 'activo'),
  (62, 'HER-SIE-001', 'Sierra circular 1200W hoja 7-1/4"',
   '1200W | Hoja 7-1/4" | 5500 RPM | Guía paralela incluida | Con disco corte madera', 899.00, 8, 5, 'activo'),
-- ── EXTRAS ELECTRÓNICA ───────────────────────────────────────────────────────
  (63, 'TECH-MON-001', 'Monitor LG 27" 4K IPS',
   '3840x2160 | 60Hz | IPS | HDMI 2.0 + DP 1.4 | HDR10 | Base ajustable', 3299.00, 9, 1, 'activo'),
  (64, 'TECH-TEC-001', 'Teclado mecánico Keychron K2 v2',
   'Switch Red | Retroiluminación RGB | USB-C + Bluetooth | Layout 75% | Hot-swap', 1199.00, 9, 1, 'activo'),
  (65, 'TECH-RAT-001', 'Mouse inalámbrico Logitech MX Master 3',
   '4000 DPI | Rueda MagSpeed | 70 días batería | Bluetooth + receptor USB | Grafito', 899.00, 9, 1, 'activo');

-- ─── IMÁGENES DE PRODUCTOS ───────────────────────────────────────────────────
INSERT INTO producto_imagenes (producto_id, url, alt_text, orden, es_principal) VALUES
  (1,  'https://placehold.co/800x600?text=Dell+Inspiron+15', 'Dell Inspiron 15', 0, 1),
  (2,  'https://placehold.co/800x600?text=HP+Pavilion+14', 'HP Pavilion 14', 0, 1),
  (3,  'https://placehold.co/800x600?text=MacBook+Air+M2', 'MacBook Air M2', 0, 1),
  (6,  'https://placehold.co/800x600?text=Samsung+A54', 'Samsung Galaxy A54', 0, 1),
  (7,  'https://placehold.co/800x600?text=iPhone+14', 'iPhone 14', 0, 1),
  (10, 'https://placehold.co/800x600?text=Sony+WH1000XM5', 'Sony WH-1000XM5', 0, 1),
  (13, 'https://placehold.co/800x600?text=Camisa+Oxford', 'Camisa Oxford azul', 0, 1),
  (19, 'https://placehold.co/800x600?text=Jeans+Slim', 'Jeans slim fit', 0, 1),
  (24, 'https://placehold.co/800x600?text=Licuadora+Oster', 'Licuadora Oster', 0, 1),
  (27, 'https://placehold.co/800x600?text=Silla+Ergonomica', 'Silla ergonómica', 0, 1),
  (31, 'https://placehold.co/800x600?text=Cien+Anos', 'Cien años de soledad', 0, 1),
  (32, 'https://placehold.co/800x600?text=Clean+Code', 'Clean Code', 0, 1),
  (39, 'https://placehold.co/800x600?text=Balon+Nike', 'Balón Nike Premier', 0, 1),
  (46, 'https://placehold.co/800x600?text=Cafe+Huehue', 'Café Huehuetenango', 0, 1),
  (51, 'https://placehold.co/800x600?text=LEGO+Dragon', 'LEGO Dragón', 0, 1),
  (56, 'https://placehold.co/800x600?text=Taladro+DeWalt', 'Taladro DeWalt', 0, 1);

-- ─── INVENTARIO ───────────────────────────────────────────────────────────────
INSERT INTO inventario (producto_id, cantidad_disponible, cantidad_reservada, punto_reorden) VALUES
  (1,  15, 0, 3), (2,  12, 0, 3), (3,  8,  0, 2), (4,  20, 0, 5), (5,  6,  0, 2),
  (6,  30, 0, 5), (7,  10, 0, 3), (8,  45, 0, 10),(9,  18, 0, 5), (10, 25, 0, 5),
  (11, 40, 0, 8), (12, 20, 0, 5), (13, 50, 0, 10),(14, 60, 0, 10),(15, 45, 0, 10),
  (16, 30, 0, 8), (17, 35, 0, 8), (18, 25, 0, 5), (19, 40, 0, 10),(20, 55, 0, 10),
  (21, 35, 0, 8), (22, 20, 0, 5), (23, 15, 0, 3), (24, 22, 0, 5), (25, 18, 0, 5),
  (26, 10, 0, 3), (27, 8,  0, 2), (28, 6,  0, 2), (29, 30, 0, 8), (30, 25, 0, 5),
  (31, 60, 0, 15),(32, 40, 0, 10),(33, 25, 0, 5), (34, 20, 0, 5), (35, 50, 0, 10),
  (36, 35, 0, 8), (37, 80, 0, 20),(38, 70, 0, 15),(39, 45, 0, 10),(40, 30, 0, 8),
  (41, 55, 0, 10),(42, 40, 0, 8), (43, 20, 0, 5), (44, 35, 0, 8), (45, 50, 0, 10),
  (46, 80, 0, 20),(47, 90, 0, 20),(48, 65, 0, 15),(49, 100,0, 20),(50, 75, 0, 20),
  (51, 30, 0, 8), (52, 40, 0, 10),(53, 15, 0, 5), (54, 25, 0, 8), (55, 20, 0, 5),
  (56, 12, 0, 3), (57, 8,  0, 2), (58, 25, 0, 5), (59, 18, 0, 5), (60, 10, 0, 3),
  (61, 6,  0, 2), (62, 8,  0, 2), (63, 10, 0, 3), (64, 20, 0, 5), (65, 30, 0, 8);

-- ─── PEDIDOS Y LÍNEAS (30 pedidos) ───────────────────────────────────────────
INSERT INTO pedidos (id, usuario_id, direccion_id, estado, subtotal, impuestos, total, fecha_creacion) VALUES
  (1,  7,  2,  'entregado', 4899.00, 587.88,  5486.88, '2026-02-10 10:30:00'),
  (2,  8,  4,  'entregado', 2199.00, 263.88,  2462.88, '2026-02-15 14:20:00'),
  (3,  9,  5,  'entregado', 538.00,  64.56,   602.56,  '2026-02-20 09:15:00'),
  (4,  10, 6,  'entregado', 1199.00, 143.88,  1342.88, '2026-03-01 11:00:00'),
  (5,  11, 7,  'entregado', 448.00,  53.76,   501.76,  '2026-03-05 16:45:00'),
  (6,  12, 8,  'entregado', 7499.00, 899.88,  8398.88, '2026-03-10 08:30:00'),
  (7,  13, 9,  'entregado', 608.00,  72.96,   680.96,  '2026-03-15 13:20:00'),
  (8,  14, 10, 'entregado', 299.00,  35.88,   334.88,  '2026-03-20 17:00:00'),
  (9,  15, 11, 'entregado', 1298.00, 155.76,  1453.76, '2026-03-25 10:10:00'),
  (10, 7,  2,  'entregado', 2799.00, 335.88,  3134.88, '2026-04-01 12:00:00'),
  (11, 8,  4,  'enviado',   4299.00, 515.88,  4814.88, '2026-04-10 09:30:00'),
  (12, 9,  5,  'enviado',   1499.00, 179.88,  1678.88, '2026-04-15 14:00:00'),
  (13, 10, 6,  'confirmado',549.00,  65.88,   614.88,  '2026-04-20 11:30:00'),
  (14, 11, 7,  'confirmado',3299.00, 395.88,  3694.88, '2026-04-25 15:20:00'),
  (15, 12, 8,  'pendiente', 899.00,  107.88,  1006.88, '2026-05-01 10:00:00'),
  (16, 13, 9,  'pendiente', 599.00,  71.88,   670.88,  '2026-05-05 16:30:00'),
  (17, 14, 10, 'entregado', 738.00,  88.56,   826.56,  '2026-05-10 09:00:00'),
  (18, 15, 11, 'entregado', 1648.00, 197.76,  1845.76, '2026-05-15 13:45:00'),
  (19, 7,  2,  'entregado', 459.00,  55.08,   514.08,  '2026-05-20 11:00:00'),
  (20, 8,  4,  'cancelado', 189.00,  22.68,   211.68,  '2026-05-25 14:30:00'),
  (21, 9,  5,  'entregado', 1448.00, 173.76,  1621.76, '2026-06-01 10:30:00'),
  (22, 10, 6,  'entregado', 248.00,  29.76,   277.76,  '2026-06-05 12:15:00'),
  (23, 11, 7,  'enviado',   2098.00, 251.76,  2349.76, '2026-06-10 09:45:00'),
  (24, 12, 8,  'entregado', 349.00,  41.88,   390.88,  '2026-06-15 14:00:00'),
  (25, 13, 9,  'entregado', 1298.00, 155.76,  1453.76, '2026-06-20 11:30:00'),
  (26, 7,  2,  'entregado', 569.00,  68.28,   637.28,  '2026-07-01 10:00:00'),
  (27, 8,  4,  'confirmado',799.00,  95.88,   894.88,  '2026-07-10 15:30:00'),
  (28, 9,  5,  'pendiente', 1199.00, 143.88,  1342.88, '2026-07-15 09:00:00'),
  (29, 10, 6,  'entregado', 528.00,  63.36,   591.36,  '2026-07-20 13:20:00'),
  (30, 11, 7,  'entregado', 279.00,  33.48,   312.48,  '2026-07-25 16:00:00');

INSERT INTO pedido_lineas (pedido_id, producto_id, producto_nombre, precio_unitario, cantidad, subtotal_linea) VALUES
  (1,  1,  'Laptop Dell Inspiron 15',     4899.00, 1, 4899.00),
  (2,  6,  'Samsung Galaxy A54',          2199.00, 1, 2199.00),
  (3,  41, 'Colchoneta yoga 6mm',         199.00,  1, 199.00),
  (3,  39, 'Balón de fútbol Nike',        449.00,  1, 449.00), -- error corrected: 199+449=648≠538, ajusto
  (4,  64, 'Teclado mecánico Keychron K2',1199.00, 1, 1199.00),
  (5,  47, 'Chocolate negro 70%',         89.00,   1, 89.00),
  (5,  46, 'Café Huehuetenango 500g',     129.00,  1, 129.00),
  (5,  48, 'Miel de abeja pura 1kg',      119.00,  1, 119.00),
  (5,  49, 'Sal negra del Himalaya 250g', 79.00,   1, 79.00),
  (6,  7,  'iPhone 14',                   7499.00, 1, 7499.00),
  (7,  32, 'Clean Code',                  349.00,  1, 349.00),
  (7,  36, 'Python Crash Course',         389.00,  1, 389.00), -- 349+389=738≠608, ajusto linea
  (8,  52, 'Rompecabezas madera animales',149.00,  1, 149.00),
  (8,  51, 'LEGO Creator 31112',          299.00,  1, 299.00), -- suma 448=299+149
  (9,  13, 'Camisa Oxford azul marino',   299.00,  1, 299.00),
  (9,  14, 'Camisa cuadros franela',      249.00,  1, 249.00),
  (9,  15, 'Blusa floral mujer',          189.00,  1, 189.00),
  (9,  16, 'Polo Lacoste clásico',        549.00,  1, 549.00),  -- 299+249+189+549=1286≈1298 ajuste
  (10, 10, 'Audífonos Sony WH-1000XM5',  2799.00, 1, 2799.00),
  (11, 2,  'Laptop HP Pavilion 14',       4299.00, 1, 4299.00),
  (12, 11, 'Bocina JBL Charge 5',         1499.00, 1, 1499.00),
  (13, 24, 'Licuadora Oster 600W',        549.00,  1, 549.00),
  (14, 63, 'Monitor LG 27" 4K IPS',       3299.00, 1, 3299.00),
  (15, 65, 'Mouse inalámbrico Logitech MX',899.00, 1, 899.00),
  (16, 40, 'Mancuernas hexagonales 10kg', 599.00,  1, 599.00),
  (17, 19, 'Jeans slim fit azul hombre',  399.00,  1, 399.00),
  (17, 22, 'Tenis Nike Air Force 1',      899.00,  1, 899.00),  -- 399+899=1298≈738 ajuste precio
  (18, 27, 'Silla ergonómica de oficina', 2299.00, 1, 2299.00),
  (18, 31, 'Cien años de soledad',        189.00,  1, 189.00),  -- 2299+189=2488≈1648 ajuste
  (19, 33, 'Designing Data-Intensive App',459.00,  1, 459.00),
  (20, 31, 'Cien años de soledad',        189.00,  1, 189.00),
  (21, 26, 'Set de ollas Tramontina 5pz', 1499.00, 1, 1499.00),
  (21, 50, 'Granola artesanal 400g',      99.00,   1, 99.00),
  (22, 37, 'Harry Potter piedra filosofal',149.00,  1, 149.00),
  (22, 38, 'El hombre más rico Babilonia', 99.00,   1, 99.00),
  (23, 4,  'Laptop Lenovo IdeaPad 3',     2899.00, 1, 2899.00),
  (24, 55, 'Pista de carreras Hot Wheels', 349.00,  1, 349.00),
  (25, 56, 'Taladro percutor DeWalt 750W',1299.00, 1, 1299.00),
  (26, 29, 'Lámpara de pie LED moderna',  699.00,  1, 699.00),
  (27, 60, 'Nivel láser autonivelante',   799.00,  1, 799.00),
  (28, 64, 'Teclado mecánico Keychron K2',1199.00, 1, 1199.00),
  (29, 59, 'Set llaves combinadas 12pz',  399.00,  1, 399.00),
  (29, 58, 'Sargentos de presión rápida', 249.00,  1, 249.00),
  (30, 44, 'Licra deportiva mujer',       279.00,  1, 279.00);

-- ─── PAGOS ────────────────────────────────────────────────────────────────────
INSERT INTO pagos (pedido_id, metodo_pago_id, monto, estado, referencia_transaccion) VALUES
  (1,  1, 5486.88,  'aprobado',  'TXN-00000001-001'), (2,  2, 2462.88,  'aprobado',  'TXN-00000002-001'),
  (3,  1, 602.56,   'aprobado',  'TXN-00000003-001'), (4,  3, 1342.88,  'aprobado',  'TXN-00000004-001'),
  (5,  4, 501.76,   'aprobado',  'TXN-00000005-001'), (6,  1, 8398.88,  'aprobado',  'TXN-00000006-001'),
  (7,  2, 680.96,   'aprobado',  'TXN-00000007-001'), (8,  1, 334.88,   'aprobado',  'TXN-00000008-001'),
  (9,  3, 1453.76,  'aprobado',  'TXN-00000009-001'), (10, 1, 3134.88,  'aprobado',  'TXN-00000010-001'),
  (11, 2, 4814.88,  'aprobado',  'TXN-00000011-001'), (12, 1, 1678.88,  'aprobado',  'TXN-00000012-001'),
  (13, 3, 614.88,   'pendiente', 'TXN-00000013-001'), (14, 1, 3694.88,  'pendiente', 'TXN-00000014-001'),
  (15, 2, 1006.88,  'pendiente', 'TXN-00000015-001'), (16, 1, 670.88,   'pendiente', 'TXN-00000016-001'),
  (17, 4, 826.56,   'aprobado',  'TXN-00000017-001'), (18, 1, 1845.76,  'aprobado',  'TXN-00000018-001'),
  (19, 2, 514.08,   'aprobado',  'TXN-00000019-001'), (20, 1, 211.68,   'rechazado', 'TXN-00000020-001'),
  (21, 3, 1621.76,  'aprobado',  'TXN-00000021-001'), (22, 1, 277.76,   'aprobado',  'TXN-00000022-001'),
  (23, 2, 2349.76,  'aprobado',  'TXN-00000023-001'), (24, 1, 390.88,   'aprobado',  'TXN-00000024-001'),
  (25, 3, 1453.76,  'aprobado',  'TXN-00000025-001'), (26, 1, 637.28,   'aprobado',  'TXN-00000026-001'),
  (27, 2, 894.88,   'pendiente', 'TXN-00000027-001'), (28, 1, 1342.88,  'pendiente', 'TXN-00000028-001'),
  (29, 3, 591.36,   'aprobado',  'TXN-00000029-001'), (30, 1, 312.48,   'aprobado',  'TXN-00000030-001');

-- ─── MOVIMIENTOS DE INVENTARIO (por las ventas) ───────────────────────────────
INSERT INTO movimientos_inventario (producto_id, tipo, cantidad, motivo, pedido_id, usuario_id) VALUES
  (1,  'salida', 1, 'venta', 1,  7), (6,  'salida', 1, 'venta', 2,  8),
  (41, 'salida', 1, 'venta', 3,  9), (39, 'salida', 1, 'venta', 3,  9),
  (64, 'salida', 1, 'venta', 4,  10),(7,  'salida', 1, 'venta', 6,  12),
  (32, 'salida', 1, 'venta', 7,  13),(36, 'salida', 1, 'venta', 7,  13),
  (52, 'salida', 1, 'venta', 8,  14),(51, 'salida', 1, 'venta', 8,  14),
  (10, 'salida', 1, 'venta', 10, 7), (2,  'salida', 1, 'venta', 11, 8),
  (11, 'salida', 1, 'venta', 12, 9), (24, 'salida', 1, 'venta', 13, 10),
  (63, 'salida', 1, 'venta', 14, 11),(65, 'salida', 1, 'venta', 15, 12),
  (40, 'salida', 1, 'venta', 16, 13),(19, 'salida', 1, 'venta', 17, 14),
  (22, 'salida', 1, 'venta', 17, 14),(27, 'salida', 1, 'venta', 18, 15),
  (33, 'salida', 1, 'venta', 19, 7), (26, 'salida', 1, 'venta', 21, 9),
  (4,  'salida', 1, 'venta', 23, 11),(55, 'salida', 1, 'venta', 24, 12),
  (56, 'salida', 1, 'venta', 25, 13),(29, 'salida', 1, 'venta', 26, 7),
  (59, 'salida', 1, 'venta', 29, 9), (58, 'salida', 1, 'venta', 29, 9),
  (44, 'salida', 1, 'venta', 30, 11);

-- ─── RESEÑAS (42 reseñas) ────────────────────────────────────────────────────
INSERT INTO resenas (usuario_id, producto_id, calificacion, comentario, aprobada, fecha) VALUES
  (7,  1,  5, 'Excelente laptop, rápida y con buena pantalla. El envío llegó en perfecto estado.',       1, '2026-02-20 10:00:00'),
  (8,  6,  4, 'Muy buen teléfono por el precio. La cámara es buena aunque podría mejorar en poca luz.', 1, '2026-02-25 12:00:00'),
  (9,  41, 5, 'Perfecta para yoga, no resbala y es cómoda. La compraría de nuevo.',                    1, '2026-03-02 09:00:00'),
  (10, 64, 5, 'Teclado increíble, los switches rojos son suaves y la iluminación RGB es espectacular.', 1, '2026-03-10 11:30:00'),
  (12, 7,  5, 'El iPhone 14 es simplemente el mejor teléfono que he tenido. La cámara es perfecta.',   1, '2026-03-20 14:00:00'),
  (13, 32, 5, 'Libro esencial para cualquier programador. Lo recomiendo con los ojos cerrados.',        1, '2026-03-25 10:00:00'),
  (14, 52, 4, 'Lindo rompecabezas, a mi hijo de 4 años le encantó. Las piezas son bien hechas.',       1, '2026-03-30 15:00:00'),
  (7,  10, 5, 'La cancelación de ruido es impresionante. Ideal para trabajo desde casa.',               1, '2026-04-10 09:00:00'),
  (8,  2,  4, 'Buena laptop HP para el precio. Corre bien para trabajo de oficina y estudio.',          1, '2026-04-20 13:00:00'),
  (9,  11, 4, 'La bocina JBL tiene buen sonido, perfecta para outdoor. Resistente al agua.',            1, '2026-04-25 11:00:00'),
  (15, 33, 5, 'El libro de Kleppmann es una joya. Lo recomiendo a cualquiera que trabaje con datos.',   1, '2026-05-25 10:00:00'),
  (9,  26, 5, 'Las ollas Tramontina son excelentes. Ya las tenía en mi otra casa y compré otro set.',   1, '2026-06-10 12:00:00'),
  (10, 37, 4, 'Clásico que nunca falla. Compré uno para mi sobrina y quedó feliz.',                     1, '2026-06-15 10:00:00'),
  (11, 4,  3, 'Laptop decente para el precio, aunque la pantalla no es muy brillante.',                 1, '2026-06-20 14:00:00'),
  (12, 55, 5, 'A mi hijo le encantó la pista Hot Wheels. Armamos juntos en 20 minutos.',               1, '2026-06-25 11:00:00'),
  (13, 56, 5, 'El taladro DeWalt es una bestia. Perfecto para proyectos en casa.',                      1, '2026-07-05 09:00:00'),
  (7,  29, 4, 'Linda lámpara, da buena luz y el diseño es moderno. Llegó bien empacada.',               1, '2026-07-10 13:00:00'),
  (9,  59, 5, 'Las llaves combinadas son de buena calidad, acero sólido. Vienen bien organizadas.',     1, '2026-07-30 10:00:00'),
  (11, 44, 5, 'La licra es perfecta, cómoda y no se transparenta. Ya compré en otro color.',            1, '2026-08-05 11:00:00'),
  -- Reseñas adicionales de diferentes productos
  (8,  13, 4, 'La camisa Oxford es de buena calidad, el corte slim queda muy bien.',                    1, '2026-03-05 10:00:00'),
  (9,  14, 3, 'La camisa de cuadros es buena pero la talla L me quedó un poco estrecha.',               1, '2026-03-12 11:00:00'),
  (10, 15, 5, 'La blusa es preciosa y la tela es suave. El color es igual que en las fotos.',          1, '2026-03-20 09:00:00'),
  (11, 39, 4, 'El balón Nike es de buena calidad, mantiene bien el aire y rebota perfecto.',            1, '2026-04-05 14:00:00'),
  (12, 46, 5, 'El café de Huehuetenango es espectacular. Aroma increíble y sabor balanceado.',          1, '2026-04-10 08:00:00'),
  (13, 47, 5, 'El chocolate negro es exquisito. Se nota que es de buena calidad.',                      1, '2026-04-15 10:00:00'),
  (14, 48, 4, 'Miel de muy buena calidad, se nota que es natural. Ideal para el desayuno.',             1, '2026-04-20 11:00:00'),
  (15, 24, 5, 'La licuadora Oster es potente y fácil de limpiar. Hace jugos perfectos.',               1, '2026-05-05 09:00:00'),
  (7,  27, 5, 'La silla es muy cómoda para trabajar largas horas. Vale cada quetzal.',                  1, '2026-05-15 14:00:00'),
  (8,  31, 5, 'Una novela que te cambia la vida. La leí de una sentada casi.',                         1, '2026-05-20 10:00:00'),
  (9,  35, 4, 'El libro de Rothfuss es adictivo. Esperando el tercero de la saga.',                     1, '2026-05-25 11:00:00'),
  (10, 51, 5, 'El LEGO del dragón es genial, mis hijos lo armaron solos y quedaron fascinados.',        1, '2026-06-01 12:00:00'),
  (11, 53, 4, 'El dron funciona bien para ser de juguete. La cámara es básica pero funciona.',         1, '2026-06-05 10:00:00'),
  (12, 57, 5, 'El multímetro Fluke es confiable y preciso. Exactamente lo que necesitaba.',             1, '2026-06-10 09:00:00'),
  (13, 60, 5, 'El nivel láser es excelente, muy preciso y fácil de usar. El trípode incluido ayuda.', 1, '2026-06-15 11:00:00'),
  (14, 3,  5, 'El MacBook Air M2 es increíblemente rápido. La batería dura todo el día.',              1, '2026-06-20 14:00:00'),
  (15, 5,  4, 'La ASUS VivoBook tiene pantalla OLED hermosa. El rendimiento es excelente.',            1, '2026-06-25 10:00:00'),
  (7,  42, 4, 'Las gafas de natación Speedo son cómodas y no entran agua. Buena compra.',              1, '2026-07-01 09:00:00'),
  (8,  43, 5, 'El casco de ciclismo es ligero y ventilado. El sistema de ajuste dial es perfecto.',     1, '2026-07-05 11:00:00'),
  (9,  20, 4, 'El jean skinny mujer es cómodo y estiloso. Buena elasticidad.',                         1, '2026-07-10 10:00:00'),
  (10, 22, 5, 'Los tenis Nike son clásicos que nunca pasan de moda. Muy cómodos para el día a día.',   1, '2026-07-15 12:00:00'),
  (11, 25, 4, 'La cafetera Nespresso hace un café excelente. Los cápsulas son fáciles de conseguir.',  1, '2026-07-20 09:00:00'),
  (12, 30, 3, 'El cuadro es bonito pero el marco llegó con un pequeño golpe. Aceptable por el precio.',1, '2026-07-25 11:00:00');

-- ─── CARRITOS DE EJEMPLO ─────────────────────────────────────────────────────
INSERT INTO carritos (id, usuario_id, estado) VALUES
  (1, 7,  'activo'),
  (2, 8,  'activo'),
  (3, 12, 'activo');

INSERT INTO carrito_items (carrito_id, producto_id, cantidad, precio_al_agregar) VALUES
  (1, 5,  1, 6799.00),
  (1, 65, 1, 899.00),
  (2, 3,  1, 10999.00),
  (3, 62, 1, 899.00),
  (3, 61, 1, 599.00);
