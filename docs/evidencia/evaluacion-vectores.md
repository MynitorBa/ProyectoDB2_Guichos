# Evaluación de la búsqueda por vectores (fase 7)

Generado por `backend/scripts/evaluar_vectores.py` el 2026-10-30 12:19. Catálogo de 69 productos activos; 35 consultas etiquetadas a mano (`backend/scripts/evaluacion/consultas.json`). Los productos de prueba creados durante el desarrollo («CER», «Gadieles», «Ferxo»…) siguen en el índice y cuentan como no relevantes.

Métricas: **P@5** (relevantes entre los 5 primeros / 5), **R@5** (relevantes encontrados en los 5 primeros / total de relevantes), **MRR** (1 / posición del primer relevante) y **Éxito@5** (consultas con al menos un relevante en los 5 primeros).

## 1. Búsqueda: texto, vectores e híbrida

**Todas las consultas**

| Método | P@5 | R@5 | MRR | Éxito@5 |
|---|---|---|---|---|
| Solo texto (Entrega 3) | 0.24 | 0.565 | 0.624 | 0.657 |
| Solo vectores | 0.331 | 0.771 | 0.745 | 0.857 |
| Vectores con umbral | 0.246 | 0.612 | 0.683 | 0.771 |
| Híbrida (producción) | 0.337 | 0.8 | 0.824 | 0.886 |

**Exactas**

| Método | P@5 | R@5 | MRR | Éxito@5 |
|---|---|---|---|---|
| Solo texto (Entrega 3) | 0.38 | 0.93 | 1.0 | 1.0 |
| Solo vectores | 0.36 | 0.935 | 0.933 | 1.0 |
| Vectores con umbral | 0.36 | 0.935 | 0.933 | 1.0 |
| Híbrida (producción) | 0.4 | 0.98 | 1.0 | 1.0 |

**Errores y sinónimos**

| Método | P@5 | R@5 | MRR | Éxito@5 |
|---|---|---|---|---|
| Solo texto (Entrega 3) | 0.425 | 0.85 | 1.0 | 1.0 |
| Solo vectores | 0.325 | 0.613 | 0.618 | 0.75 |
| Vectores con umbral | 0.15 | 0.269 | 0.417 | 0.5 |
| Híbrida (producción) | 0.475 | 0.975 | 0.938 | 1.0 |

**Lenguaje natural**

| Método | P@5 | R@5 | MRR | Éxito@5 |
|---|---|---|---|---|
| Solo texto (Entrega 3) | 0.071 | 0.216 | 0.225 | 0.294 |
| Solo vectores | 0.318 | 0.749 | 0.694 | 0.824 |
| Vectores con umbral | 0.224 | 0.583 | 0.662 | 0.765 |
| Híbrida (producción) | 0.235 | 0.613 | 0.667 | 0.765 |

## 2. Productos similares: `more_like_this` frente a kNN

Para cada uno de los 63 productos reales, sus 5 más parecidos. Se toma como correcto que sean de la misma familia (prefijo del SKU, p. ej. `TECH-LAP`) o del mismo departamento (`TECH`).

| Método | Misma familia (P@5) | Mismo departamento (P@5) | Con resultados | Productos de prueba en el top 5 |
|---|---|---|---|---|
| more_like_this | 0.143 | 0.286 | 0.571 | 0.0 |
| knn | 0.279 | 0.717 | 1.0 | 0.044 |

## 3. Modelos (búsqueda exacta en memoria)

| Modelo | Dims | Carga (s) | ms por producto | P@5 | MRR | MRR natural | Máx. sin sentido |
|---|---|---|---|---|---|---|---|
| MiniLM-L12 (384) | 384 | 0.9 | 8.1 | 0.291 | 0.664 | 0.706 | 0.507 |
| mpnet (768) | 768 | 2.2 | 21.7 | 0.337 | 0.745 | 0.695 | 0.417 |

**Pérdida por HNSW + int8 (mpnet (768))**: el top 10 del índice coincide en un 97.4 % con el exacto en float32.

## 4. Umbral de similitud

**MiniLM-L12 (384)** (consultas naturales y de tolerancia; «sin sentido»: resultados que pasan el umbral para 6 consultas sin productos relacionados)

| Umbral | Precisión | Cobertura | Resultados sin sentido |
|---|---|---|---|
| 0.35 | 0.324 | 0.655 | 11 |
| 0.4 | 0.375 | 0.491 | 5 |
| 0.45 | 0.472 | 0.309 | 2 |
| 0.5 | 0.526 | 0.182 | 1 |
| 0.55 | 0.25 | 0.036 | 0 |
| 0.6 | 0.0 | 0.0 | 0 |

**mpnet (768)** (consultas naturales y de tolerancia; «sin sentido»: resultados que pasan el umbral para 6 consultas sin productos relacionados)

| Umbral | Precisión | Cobertura | Resultados sin sentido |
|---|---|---|---|
| 0.35 | 0.285 | 0.745 | 3 |
| 0.4 | 0.354 | 0.618 | 1 |
| 0.45 | 0.441 | 0.473 | 0 |
| 0.5 | 0.519 | 0.255 | 0 |
| 0.55 | 0.556 | 0.182 | 0 |
| 0.6 | 0.583 | 0.127 | 0 |

## Detalle por consulta (top 5 de cada método)

| Consulta | Tipo | Texto | Híbrida | Vectores |
|---|---|---|---|---|
| samsung | exacta | TECH-CEL-001 | TECH-CEL-001, TECH-CEL-003, TECH-CEL-004 | TECH-CEL-001, TECH-CEL-003, TECH-CEL-004, TECH-CEL-002, TECH-AUD-001 |
| laptop | exacta | TECH-LAP-001, PCU-050AB025, TECH-LAP-005, TECH-LAP-002, TECH-LAP-004 | TECH-LAP-001, PCU-050AB025, TECH-LAP-005, TECH-LAP-002, TECH-LAP-004 | PCU-AB7CEE94, PCU-050AB025, TECH-LAP-002, TECH-LAP-005, TECH-LAP-001 |
| licuadora | exacta | HOGAR-COC-001 | HOGAR-COC-001 | HOGAR-COC-001, LIBRO-TEC-001, DEP-ROP-002, HOGAR-COC-002, HER-TAL-001 |
| audífonos | exacta | TECH-AUD-001 | TECH-AUD-001, TECH-AUD-003 | TECH-AUD-003, TECH-AUD-001, HER-ESM-001, TECH-AUD-002, JUG-91EA5E10 |
| pantalones | exacta | ROPA-PAN-003, ROPA-PAN-001, ROPA-PAN-002 | ROPA-PAN-003, ROPA-PAN-001, ROPA-PAN-002, ROPA-CAL-001, ROPA-CAL-002 | ROPA-PAN-003, ROPA-PAN-001, ROPA-CAL-001, ROPA-PAN-002, ROPA-CAL-002 |
| café | exacta | ALI-CAF-001, HOGAR-COC-002 | ALI-CAF-001, HOGAR-COC-002 | HOGAR-COC-002, ALI-CAF-001, ROPA-CAM-004, LUI-6525CEC3, ALI-MIE-001 |
| camisa | exacta | ROPA-CAM-002, ROPA-CAM-001, ROPA-CAM-005, ROPA-CAM-003, ROPA-CAM-004 | ROPA-CAM-002, ROPA-CAM-001, ROPA-CAM-005, ROPA-CAM-004, ROPA-CAM-003 | ROPA-CAM-004, ROPA-CAM-002, ROPA-CAM-001, ROPA-PAN-003, ROPA-CAM-006 |
| harry potter | exacta | LIBRO-FIC-003 | LIBRO-FIC-003 | LIBRO-FIC-003, LIBRO-FIC-002, LIBRO-TEC-003, LIBRO-AUT-001, LIBRO-FIC-001 |
| taladro | exacta | HER-TAL-001 | HER-TAL-001, DEP-ROP-002, HOGAR-COC-001, LUI-833084D6, JUG-91EA5E10 | HER-TAL-001, DEP-ROP-002, HOGAR-COC-001, LUI-833084D6, JUG-91EA5E10 |
| monitor | exacta | TECH-MON-001 | TECH-MON-001, PCU-050AB025, TECH-RAT-001 | TECH-MON-001, PCU-050AB025, TECH-RAT-001, PCU-AB7CEE94, HOGAR-MUE-001 |
| macbok | tolerancia | TECH-LAP-003 | TECH-LAP-003 | LIBRO-TEC-003, TECH-LAP-003, HOGAR-MUE-002, JUG-91EA5E10, PCU-AB7CEE94 |
| telefono | tolerancia | TECH-CEL-004, TECH-CEL-001, TECH-CEL-003, TECH-CEL-002 | TECH-CEL-004, TECH-CEL-001, TECH-CEL-003, TECH-CEL-002 | TECH-CEL-004, HOGAR-MUE-001, TECH-CEL-001, TECH-AUD-001, TECH-CEL-003 |
| zapatillas | tolerancia | ROPA-CAL-001 | ROPA-CAL-001, JUG-91EA5E10, LUI-6525CEC3, ROPA-CAM-003, LUI-833084D6 | JUG-91EA5E10, LUI-6525CEC3, ROPA-CAM-003, LUI-833084D6, DEP-ROP-002 |
| audifonos inalambricos | tolerancia | TECH-AUD-001, TECH-RAT-001 | TECH-AUD-003, TECH-AUD-001, TECH-RAT-001 | TECH-AUD-003, HER-TAL-001, LUI-833084D6, LUI-6525CEC3, TECH-AUD-001 |
| computadora portatil | tolerancia | TECH-LAP-001, PCU-050AB025, TECH-LAP-005, TECH-LAP-002, TECH-LAP-004 | PCU-050AB025, TECH-LAP-005, TECH-LAP-002, TECH-LAP-004, TECH-LAP-001 | PCU-AB7CEE94, PCU-050AB025, TECH-LAP-002, TECH-LAP-004, HOGAR-MUE-001 |
| celular | tolerancia | TECH-CEL-004, TECH-CEL-001, TECH-CEL-003, TECH-CEL-002 | TECH-CEL-004, TECH-CEL-001, TECH-CEL-003, TECH-CEL-002 | TECH-CEL-004, TECH-CEL-001, TECH-CEL-003, HOGAR-MUE-001, TECH-AUD-001 |
| zapatos | tolerancia | ROPA-CAL-002 | ROPA-CAL-002, ROPA-CAL-001, DEP-ROP-001 | ROPA-CAL-002, ROPA-CAL-001, DEP-ROP-001, ROPA-PAN-003, HOGAR-MUE-001 |
| multimetro | tolerancia | HER-MED-001 | HER-MED-001, HER-NIV-001 | HER-NIV-001, HER-TAL-001, HER-ESM-001, HOGAR-MUE-002, DEP-GIM-001 |
| algo para escuchar música sin cables | natural | — | TECH-AUD-003, TECH-AUD-001 | TECH-AUD-003, TECH-AUD-001, TECH-AUD-002, HER-ESM-001, HOGAR-MUE-001 |
| herramienta para hacer agujeros en la pared | natural | — | — | HOGAR-DEC-002, HOGAR-COC-003, JUG-MAD-001, HOGAR-MUE-002, HOGAR-MUE-001 |
| celular con buena cámara | natural | — | TECH-CEL-001, TECH-CEL-004, JUG-ELE-001, TECH-CEL-003 | TECH-CEL-001, TECH-CEL-004, JUG-ELE-001, TECH-CEL-003, TECH-CEL-002 |
| regalo para un niño de 6 años | natural | — | JUG-91EA5E10, JUG-MUÃ‘-001 | JUG-91EA5E10, JUG-MUÃ‘-001, JUG-ARM-001, JUG-MAD-001, HOGAR-DEC-002 |
| libro para aprender a programar | natural | — | LIBRO-TEC-001, LIBRO-TEC-002 | LIBRO-TEC-001, LIBRO-TEC-002, LIBRO-TEC-003, PCU-AB7CEE94, LIBRO-FIC-003 |
| novela de fantasía | natural | HER-NIV-001 | LIBRO-FIC-003, LIBRO-FIC-001, HER-NIV-001 | LIBRO-FIC-003, LIBRO-FIC-001, LIBRO-FIC-002, LUI-833084D6, LUI-6525CEC3 |
| algo para hacer ejercicio en casa | natural | — | HOGAR-MUE-001, DEP-GIM-002, DEP-GIM-001 | HOGAR-MUE-001, DEP-GIM-002, DEP-GIM-001, JUG-MUÃ‘-001, DEP-ROP-001 |
| preparar batidos | natural | — | JUG-91EA5E10, JUG-MAD-001, ALI-MIE-001 | JUG-91EA5E10, JUG-MAD-001, ALI-MIE-001, HOGAR-COC-003, DEP-ROP-002 |
| desayuno saludable | natural | — | ALI-GRA-001 | ALI-GRA-001, ALI-MIE-001, HOGAR-COC-002, DEP-GIM-001, ALI-CAF-001 |
| muebles para la oficina | natural | HOGAR-MUE-001 | HOGAR-MUE-001, HOGAR-MUE-002, HOGAR-DEC-002 | HOGAR-MUE-001, HOGAR-MUE-002, HOGAR-DEC-002, PCU-050AB025, PCU-AB7CEE94 |
| iluminación para la sala | natural | — | HOGAR-DEC-001, HOGAR-MUE-002, HOGAR-MUE-001 | HOGAR-DEC-001, HOGAR-MUE-002, HOGAR-MUE-001, HER-ESM-001, LIBRO-TEC-001 |
| medir voltaje | natural | ALI-CAF-001 | HER-MED-001, HER-TAL-001, ALI-CAF-001 | HER-MED-001, HER-TAL-001, HOGAR-DEC-001, HER-NIV-001, HER-SAR-001 |
| cortar madera | natural | HOGAR-MUE-002, JUG-MAD-001, HER-SIE-001, HOGAR-DEC-002 | JUG-MAD-001, HER-SIE-001, HOGAR-MUE-002, HOGAR-DEC-002 | HER-SIE-001, JUG-MAD-001, HOGAR-MUE-002, HOGAR-DEC-002, HOGAR-DEC-001 |
| accesorios para la computadora | natural | TECH-LAP-001, TECH-RAT-001, TECH-LAP-005, TECH-LAP-002, TECH-MON-001 | PCU-AB7CEE94, PCU-050AB025, TECH-RAT-001, TECH-LAP-002, TECH-LAP-004 | PCU-AB7CEE94, PCU-050AB025, HOGAR-MUE-001, TECH-RAT-001, TECH-LAP-002 |
| aprender sobre bases de datos | natural | LIBRO-EDU-001 | LIBRO-EDU-001, LIBRO-TEC-002 | LIBRO-TEC-002, LIBRO-EDU-001, LIBRO-TEC-003, LIBRO-TEC-001, PCU-AB7CEE94 |
| juguete que vuela | natural | JUG-ELE-001, JUG-91EA5E10, JUG-ARM-001, JUG-CAR-001, JUG-MAD-001 | JUG-ELE-001, JUG-91EA5E10, JUG-MUÃ‘-001, JUG-ARM-001, JUG-CAR-001 | JUG-91EA5E10, JUG-ELE-001, JUG-MUÃ‘-001, JUG-ARM-001, HOGAR-MUE-001 |
| cómo manejar mejor mi dinero | natural | — | — | HER-ESM-001, ROPA-PAN-003, JUG-91EA5E10, HOGAR-MUE-002, JUG-MAD-001 |
