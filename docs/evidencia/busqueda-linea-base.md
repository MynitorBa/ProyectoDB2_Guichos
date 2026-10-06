# Comparación de búsqueda de productos

Generado por `backend/scripts/comparar_busqueda.py`. Un acierto significa que un producto esperado aparece entre los 3 primeros resultados. La latencia es el promedio de 5 ejecuciones.

| Consulta | Tipo | MongoDB $regex (actual) | MongoDB $text |
|---|---|---|---|
| `laptop` | control | ✅ 5 res. · 1.4 ms | ✅ 6 res. · 1.4 ms |
| `licuadora oster` | control | ✅ 1 res. · 1.0 ms | ✅ 1 res. · 1.5 ms |
| `lapto` | error ortográfico | ✅ 5 res. · 1.2 ms | ❌ 0 res. · 1.7 ms |
| `macbok` | error ortográfico | ❌ 0 res. · 1.1 ms | ❌ 0 res. · 1.4 ms |
| `samsng galaxy` | error ortográfico | ❌ 0 res. · 1.0 ms | ✅ 1 res. · 1.3 ms |
| `harry poter` | error ortográfico | ❌ 0 res. · 1.1 ms | ✅ 1 res. · 1.1 ms |
| `audifonos sony` | sin tilde | ❌ 0 res. · 1.2 ms | ✅ 1 res. · 1.1 ms |
| `mouse inalambrico` | sin tilde | ❌ 0 res. · 1.0 ms | ✅ 1 res. · 1.0 ms |
| `cafe huehuetenango` | sin tilde | ❌ 0 res. · 1.1 ms | ✅ 1 res. · 1.5 ms |
| `telefono` | sinónimo | ❌ 0 res. · 1.2 ms | ❌ 0 res. · 1.7 ms |
| `portatil` | sinónimo | ❌ 0 res. · 1.2 ms | ❌ 0 res. · 1.3 ms |
| `zapatillas nike` | sinónimo | ❌ 0 res. · 1.1 ms | ✅ 2 res. · 1.1 ms |
| `sams` | prefijo | ✅ 1 res. · 1.3 ms | ❌ 0 res. · 0.9 ms |
| `tala` | prefijo | ✅ 1 res. · 1.7 ms | ❌ 0 res. · 1.1 ms |
| `inspiron dell` | orden de palabras | ❌ 0 res. · 1.6 ms | ✅ 1 res. · 1.4 ms |
| `dewalt taladro` | orden de palabras | ❌ 0 res. · 1.6 ms | ✅ 1 res. · 1.4 ms |
| `TECH-LAP-001` | SKU exacto | ✅ 1 res. · 1.2 ms | ❌ 0 res. · 1.1 ms |
| **Aciertos en top 3** | | **6/17** · prom. 1.2 ms | **10/17** · prom. 1.3 ms |

### Primeros 3 resultados por consulta

| Consulta | Motor | Resultados |
|---|---|---|
| `laptop` | MongoDB $regex (actual) | Laptop Dell Inspiron 15, Laptop HP Pavilion 14, Laptop Lenovo IdeaPad 3 |
| `laptop` | MongoDB $text | CER, Laptop Alienware, Laptop Lenovo IdeaPad 3 |
| `licuadora oster` | MongoDB $regex (actual) | Licuadora Oster 600W |
| `licuadora oster` | MongoDB $text | Licuadora Oster 600W |
| `lapto` | MongoDB $regex (actual) | Laptop Dell Inspiron 15, Laptop HP Pavilion 14, Laptop Lenovo IdeaPad 3 |
| `lapto` | MongoDB $text | — |
| `macbok` | MongoDB $regex (actual) | — |
| `macbok` | MongoDB $text | — |
| `samsng galaxy` | MongoDB $regex (actual) | — |
| `samsng galaxy` | MongoDB $text | Samsung Galaxy A54 |
| `harry poter` | MongoDB $regex (actual) | — |
| `harry poter` | MongoDB $text | Harry Potter y la piedra filosofal |
| `audifonos sony` | MongoDB $regex (actual) | — |
| `audifonos sony` | MongoDB $text | Audífonos Sony WH-1000XM5 |
| `mouse inalambrico` | MongoDB $regex (actual) | — |
| `mouse inalambrico` | MongoDB $text | Mouse inalámbrico Logitech MX Master 3 |
| `cafe huehuetenango` | MongoDB $regex (actual) | — |
| `cafe huehuetenango` | MongoDB $text | Café molido artesanal Huehuetenango 500g |
| `telefono` | MongoDB $regex (actual) | — |
| `telefono` | MongoDB $text | — |
| `portatil` | MongoDB $regex (actual) | — |
| `portatil` | MongoDB $text | — |
| `zapatillas nike` | MongoDB $regex (actual) | — |
| `zapatillas nike` | MongoDB $text | Balón de fútbol Nike Premier League, Tenis Nike Air Force 1 |
| `sams` | MongoDB $regex (actual) | Samsung Galaxy A54 |
| `sams` | MongoDB $text | — |
| `tala` | MongoDB $regex (actual) | Taladro percutor DeWalt 750W |
| `tala` | MongoDB $text | — |
| `inspiron dell` | MongoDB $regex (actual) | — |
| `inspiron dell` | MongoDB $text | Laptop Dell Inspiron 15 |
| `dewalt taladro` | MongoDB $regex (actual) | — |
| `dewalt taladro` | MongoDB $text | Taladro percutor DeWalt 750W |
| `TECH-LAP-001` | MongoDB $regex (actual) | Laptop Dell Inspiron 15 |
| `TECH-LAP-001` | MongoDB $text | — |
