# Comparación de búsqueda: MongoDB frente a Elasticsearch

Generado por `backend/scripts/comparar_busqueda.py`. Un acierto significa que un producto esperado aparece entre los 3 primeros resultados. La latencia es el promedio de 5 ejecuciones.

| Consulta | Tipo | MongoDB $regex (anterior) | MongoDB $text | Elasticsearch (nuevo) |
|---|---|---|---|---|
| `laptop` | control | ✅ 5 res. · 1.1 ms | ✅ 6 res. · 0.9 ms | ✅ 6 res. · 8.2 ms |
| `licuadora oster` | control | ✅ 1 res. · 0.9 ms | ✅ 1 res. · 1.4 ms | ✅ 1 res. · 14.3 ms |
| `lapto` | error ortográfico | ✅ 5 res. · 1.1 ms | ❌ 0 res. · 0.9 ms | ✅ 5 res. · 5.6 ms |
| `macbok` | error ortográfico | ❌ 0 res. · 1.0 ms | ❌ 0 res. · 1.0 ms | ✅ 1 res. · 5.7 ms |
| `samsng galaxy` | error ortográfico | ❌ 0 res. · 1.1 ms | ✅ 1 res. · 1.0 ms | ✅ 1 res. · 7.1 ms |
| `harry poter` | error ortográfico | ❌ 0 res. · 1.3 ms | ✅ 1 res. · 1.0 ms | ✅ 1 res. · 6.9 ms |
| `audifonos sony` | sin tilde | ❌ 0 res. · 1.0 ms | ✅ 1 res. · 1.0 ms | ✅ 1 res. · 7.6 ms |
| `mouse inalambrico` | sin tilde | ❌ 0 res. · 1.0 ms | ✅ 1 res. · 1.0 ms | ✅ 1 res. · 16.2 ms |
| `cafe huehuetenango` | sin tilde | ❌ 0 res. · 1.0 ms | ✅ 1 res. · 0.9 ms | ✅ 1 res. · 17.1 ms |
| `telefono` | sinónimo | ❌ 0 res. · 1.0 ms | ❌ 0 res. · 1.0 ms | ✅ 4 res. · 7.1 ms |
| `portatil` | sinónimo | ❌ 0 res. · 1.0 ms | ❌ 0 res. · 0.9 ms | ✅ 6 res. · 14.0 ms |
| `zapatillas nike` | sinónimo | ❌ 0 res. · 1.1 ms | ✅ 2 res. · 1.0 ms | ✅ 2 res. · 12.8 ms |
| `sams` | prefijo | ✅ 1 res. · 1.1 ms | ❌ 0 res. · 1.1 ms | ✅ 1 res. · 4.8 ms |
| `tala` | prefijo | ✅ 1 res. · 1.0 ms | ❌ 0 res. · 0.8 ms | ✅ 1 res. · 5.4 ms |
| `inspiron dell` | orden de palabras | ❌ 0 res. · 1.0 ms | ✅ 1 res. · 1.0 ms | ✅ 1 res. · 12.4 ms |
| `dewalt taladro` | orden de palabras | ❌ 0 res. · 1.2 ms | ✅ 1 res. · 0.9 ms | ✅ 1 res. · 7.2 ms |
| `TECH-LAP-001` | SKU exacto | ✅ 1 res. · 1.0 ms | ❌ 0 res. · 1.1 ms | ✅ 1 res. · 6.5 ms |
| **Aciertos en top 3** | | **6/17** · prom. 1.0 ms | **10/17** · prom. 1.0 ms | **17/17** · prom. 9.4 ms |

### Primeros 3 resultados por consulta

| Consulta | Motor | Resultados |
|---|---|---|
| `laptop` | MongoDB $regex (anterior) | Laptop Dell Inspiron 15, Laptop HP Pavilion 14, Laptop Lenovo IdeaPad 3 |
| `laptop` | MongoDB $text | CER, Laptop Alienware, Laptop ASUS VivoBook 14 |
| `laptop` | Elasticsearch (nuevo) | Laptop Alienware, Laptop Dell Inspiron 15, Laptop ASUS VivoBook 14 |
| `licuadora oster` | MongoDB $regex (anterior) | Licuadora Oster 600W |
| `licuadora oster` | MongoDB $text | Licuadora Oster 600W |
| `licuadora oster` | Elasticsearch (nuevo) | Licuadora Oster 600W |
| `lapto` | MongoDB $regex (anterior) | Laptop Dell Inspiron 15, Laptop HP Pavilion 14, Laptop Lenovo IdeaPad 3 |
| `lapto` | MongoDB $text | — |
| `lapto` | Elasticsearch (nuevo) | Laptop Dell Inspiron 15, Laptop Lenovo IdeaPad 3, Laptop ASUS VivoBook 14 |
| `macbok` | MongoDB $regex (anterior) | — |
| `macbok` | MongoDB $text | — |
| `macbok` | Elasticsearch (nuevo) | MacBook Air M2 |
| `samsng galaxy` | MongoDB $regex (anterior) | — |
| `samsng galaxy` | MongoDB $text | Samsung Galaxy A54 |
| `samsng galaxy` | Elasticsearch (nuevo) | Samsung Galaxy A54 |
| `harry poter` | MongoDB $regex (anterior) | — |
| `harry poter` | MongoDB $text | Harry Potter y la piedra filosofal |
| `harry poter` | Elasticsearch (nuevo) | Harry Potter y la piedra filosofal |
| `audifonos sony` | MongoDB $regex (anterior) | — |
| `audifonos sony` | MongoDB $text | Audífonos Sony WH-1000XM5 |
| `audifonos sony` | Elasticsearch (nuevo) | Audífonos Sony WH-1000XM5 |
| `mouse inalambrico` | MongoDB $regex (anterior) | — |
| `mouse inalambrico` | MongoDB $text | Mouse inalámbrico Logitech MX Master 3 |
| `mouse inalambrico` | Elasticsearch (nuevo) | Mouse inalámbrico Logitech MX Master 3 |
| `cafe huehuetenango` | MongoDB $regex (anterior) | — |
| `cafe huehuetenango` | MongoDB $text | Café molido artesanal Huehuetenango 500g |
| `cafe huehuetenango` | Elasticsearch (nuevo) | Café molido artesanal Huehuetenango 500g |
| `telefono` | MongoDB $regex (anterior) | — |
| `telefono` | MongoDB $text | — |
| `telefono` | Elasticsearch (nuevo) | Motorola Edge 40, Xiaomi Redmi Note 12, Samsung Galaxy A54 |
| `portatil` | MongoDB $regex (anterior) | — |
| `portatil` | MongoDB $text | — |
| `portatil` | Elasticsearch (nuevo) | Laptop Alienware, Laptop Dell Inspiron 15, Laptop ASUS VivoBook 14 |
| `zapatillas nike` | MongoDB $regex (anterior) | — |
| `zapatillas nike` | MongoDB $text | Balón de fútbol Nike Premier League, Tenis Nike Air Force 1 |
| `zapatillas nike` | Elasticsearch (nuevo) | Tenis Nike Air Force 1, Balón de fútbol Nike Premier League |
| `sams` | MongoDB $regex (anterior) | Samsung Galaxy A54 |
| `sams` | MongoDB $text | — |
| `sams` | Elasticsearch (nuevo) | Samsung Galaxy A54 |
| `tala` | MongoDB $regex (anterior) | Taladro percutor DeWalt 750W |
| `tala` | MongoDB $text | — |
| `tala` | Elasticsearch (nuevo) | Taladro percutor DeWalt 750W |
| `inspiron dell` | MongoDB $regex (anterior) | — |
| `inspiron dell` | MongoDB $text | Laptop Dell Inspiron 15 |
| `inspiron dell` | Elasticsearch (nuevo) | Laptop Dell Inspiron 15 |
| `dewalt taladro` | MongoDB $regex (anterior) | — |
| `dewalt taladro` | MongoDB $text | Taladro percutor DeWalt 750W |
| `dewalt taladro` | Elasticsearch (nuevo) | Taladro percutor DeWalt 750W |
| `TECH-LAP-001` | MongoDB $regex (anterior) | Laptop Dell Inspiron 15 |
| `TECH-LAP-001` | MongoDB $text | — |
| `TECH-LAP-001` | Elasticsearch (nuevo) | Laptop Dell Inspiron 15 |
