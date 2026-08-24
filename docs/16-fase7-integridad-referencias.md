# Fase 7 — Integridad de categorías, referencias y ofertas

**Estado:** aplicada y validada el 24 de agosto de 2026.

## Objetivo

Cerrar dos relaciones que anteriormente dependían solo de convenciones de la
aplicación:

- `producto_referencias.categoria_id → categorias.id`.
- `ofertas.producto_ref → producto_referencias.producto_ref`.

MongoDB continúa siendo la autoridad del contenido descriptivo. El documento
conserva `categoria.slug` y `categoria.nombre` como snapshot útil para las
lecturas del catálogo, mientras que MySQL valida la categoría mediante FK.

## Procedimiento aplicado

El comando reproducible fue:

```powershell
powershell -ExecutionPolicy Bypass -File `
  ".\scripts\complete-phase7-reference-integrity.ps1"
```

Antes de modificar el esquema se leyó `categoria.slug` de los 65 documentos de
MongoDB y se comprobó que cada slug existiera en `categorias`. Se creó el
respaldo local ignorado por Git:

```text
backups/phase7_refs_20260824_104220.json
```

La migración `database/mysql/11_phase7_reference_integrity.sql` es idempotente:
valida los datos antes de hacer `categoria_id` obligatorio y antes de agregar
las dos restricciones.

## Resultado verificado

| Comprobación | Resultado |
|---|---:|
| Referencias de producto | 65 |
| Referencias con categoría | 65 |
| Ofertas enlazadas | 65 |
| Documentos MongoDB | 65 |
| Eventos MongoDB | 477 |
| Referencias huérfanas | 0 |
| Categorías divergentes | 0 |
| Pruebas automatizadas | 30 aprobadas |

Además:

- El verificador MySQL/MongoDB terminó con `[OK] Setup completo`.
- Las proyecciones de oferta estaban sincronizadas.
- El índice único de idempotencia del outbox estaba instalado.
- El frontend Vite compiló correctamente.
- `GET /health` respondió con estado saludable.

Como limpieza posterior, se sustituyó el uso obsoleto de `datetime.utcnow()`,
se fijó explícitamente el alcance asíncrono de pytest y se dividió el bundle de
producción. La repetición terminó con 30 pruebas sin advertencias y una
compilación Vite sin ciclos ni chunks mayores de 500 kB; el mayor quedó en
aproximadamente 450 kB.
