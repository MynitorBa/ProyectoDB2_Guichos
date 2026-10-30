# Línea base de la Entrega 4

Rama `inicio-entrega4`, creada el 30 de octubre de 2026 desde `planb_pre_entrega4`
(commit `07a2576`, idéntico en GitHub). Motores principales en Docker.

## Estado del sistema antes de empezar

| Verificación | Resultado |
|---|---|
| `pytest tests -q` | 288 aprobadas, 4 omitidas, 3 fallidas |
| `scripts/verificar_consistencia.py` | I1–I7 se cumplen |

Las 3 fallas ya existían antes del plan B y no son de esta entrega: `test_checkout_flash_convierte_reserva_y_descuenta_pool`
y las dos de `test_fulfillment_vendor_workspace` («No se identificó el inventario de la promoción flash / de esta
venta»), relacionadas con el cambio de bodegas `018935a` sobre los datos de la base principal.

## Modelo de embeddings: viabilidad en el equipo

Se usa **fastembed** (ONNX Runtime, sin PyTorch): se instaló sin problemas en Windows con Python 3.12
(`fastembed 0.9.1`). Los modelos se descargan una vez desde Hugging Face y luego funcionan sin internet.

Prueba rápida con 5 productos y 5 consultas en lenguaje natural, donde la respuesta correcta no comparte
palabras con la consulta (por ejemplo, «herramienta para hacer agujeros en la pared» → taladro):

| Modelo (multilingüe) | Dimensiones | Tamaño | Aciertos | Carga | Por texto |
|---|---|---|---|---|---|
| paraphrase-multilingual-MiniLM-L12-v2 | 384 | 0.22 GB | 3/5 | 1.0 s | 1.5 ms |
| paraphrase-multilingual-mpnet-base-v2 | 768 | 1.0 GB | 4/5 | 24 s | 4.9 ms |
| potion-multilingual-128M (estático) | 256 | 0.5 GB | 2/5 | 12.7 s | < 0.1 ms |

Conclusión: el modelo será **configurable**. La muestra es pequeña; la elección final se toma con la
evaluación sobre el catálogo real (fase 7). Cambiarlo después solo exige reindexar con un índice nuevo y
mover el alias, sin cortar el servicio.
