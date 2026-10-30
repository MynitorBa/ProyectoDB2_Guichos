"""Informe de arquitectura final de TiendaYa (Entrega final).

Un solo contenido, tres salidas:
  - docs/informe/Informe_Entrega_Final_TiendaYa.docx  (formato de la Entrega 2: Times New Roman 11,
    encabezados Aptos Display, tablas con encabezado #D9D9D9 a 9.5 pt, márgenes de 1", pie con número)
  - docs/informe/Informe_Entrega_Final_TiendaYa.pdf   (exportado por Word, con el índice actualizado)
  - docs/informe-entrega4.md                           (versión para el repositorio)

Las cifras de calidad y escala se leen de los archivos de evidencia (docs/evidencia/*.json), así el
informe no puede contradecirlos.

Uso (desde la raíz del proyecto):
    backend\\venv\\Scripts\\python.exe docs\\informe\\generar_informe_entrega4.py
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

RAIZ = Path(__file__).resolve().parents[2]
DOCS = RAIZ / 'docs'
SALIDA = DOCS / 'informe'
DOCX_OUT = SALIDA / 'Informe_Entrega_Final_TiendaYa.docx'
PDF_OUT = SALIDA / 'Informe_Entrega_Final_TiendaYa.pdf'
MD_OUT = DOCS / 'informe-entrega4.md'
DIAGRAMA = DOCS / 'diagramas' / 'arquitectura-final.png'

FONT_BODY = 'Times New Roman'
FONT_HEADING = 'Aptos Display'
NEGRO = RGBColor(0, 0, 0)

EVAL = json.loads((DOCS / 'evidencia' / 'evaluacion-vectores.json').read_text(encoding='utf-8'))
BENCH = {n: json.loads((DOCS / 'evidencia' / 'benchmark' / f'vectores_{n}.json').read_text(encoding='utf-8'))
         for n in ('100000_int8_hnsw', '100000_hnsw', '1000000_int8_hnsw')}


def f2(x: float) -> str:
    return f'{x:.2f}'


# ══ Contenido ═══════════════════════════════════════════════════════════════════
# Bloques: ('h1'|'h2'|'h3'|'p'|'b', texto) · ('t', encabezados, filas) · ('img', ruta, ancho) · ('salto',)

def contenido() -> list[tuple]:
    b = EVAL['busqueda']['resumen']
    sim = EVAL['similares']
    mod = EVAL['modelos']
    b100, b100f, b1m = BENCH['100000_int8_hnsw'], BENCH['100000_hnsw'], BENCH['1000000_int8_hnsw']
    nombres = {'texto': 'Solo texto (Entrega 3)', 'vector': 'Solo vectores', 'vector_umbral': 'Vectores con umbral 0.45',
               'hibrida': 'Híbrida (en producción)'}
    return [
        # ── 1 ───────────────────────────────────────────────────────────────────
        ('h1', '1. Introducción y alcance de la entrega final'),
        ('p', 'TiendaYa es un marketplace con persistencia políglota: cada motor de base de datos resuelve el '
              'problema para el que está mejor equipado. Las entregas anteriores incorporaron MySQL como autoridad '
              'transaccional, MongoDB para el catálogo documental, Redis para carritos y ventas flash, Cassandra y '
              'Neo4j para analítica y fraude, y Elasticsearch para la búsqueda, con un checkout distribuido como saga.'),
        ('p', 'La entrega final cierra la arquitectura con dos capacidades que suelen postergarse y que el enunciado '
              'pide de forma explícita, más los documentos de cierre:'),
        ('t', ['Criterio del enunciado', 'Peso', 'Qué se entrega', 'Sección'], [
            ['Recomendación semántica', '5 pts', 'Vectores de cada producto en Elasticsearch y un servicio de embeddings propio: '
             '«También te podría interesar» en la página de producto, «Te podría interesar» en el inicio, búsqueda híbrida '
             'y aviso de duplicados', '3'],
            ['Control de acceso en un componente NoSQL', '4 pts', 'Usuarios por servicio con mínimo privilegio en Redis (ACL), '
             'MongoDB (roles) y Elasticsearch (roles), con evidencia automática', '4'],
            ['Diagrama de arquitectura final', '3 pts', 'Todos los componentes de persistencia y sus relaciones', '2'],
            ['Retrospectiva', '4 pts', 'Qué decisiones se sostendrían y cuáles se replantearían, con justificación', '5'],
            ['Presentación', '4 pts', 'Modo presentación con los datos DEMO, ya con vectores y control de acceso', '6'],
        ]),
        ('p', 'Cada decisión se tomó con evidencia medida: una línea base antes de cambiar, una evaluación con '
              'consultas etiquetadas a mano, un benchmark de escala y pruebas automáticas que se pueden volver a '
              'ejecutar. Las decisiones se registran como ADR con la estructura del curso (contexto, alternativas, '
              'decisión, justificación y consecuencias).'),

        # ── 2 ───────────────────────────────────────────────────────────────────
        ('h1', '2. Arquitectura final'),
        ('img', DIAGRAMA, 6.5),
        ('p', 'La regla que organiza la arquitectura: MySQL decide el dinero y el inventario; los demás motores son '
              'proyecciones reconstruibles o estado efímero. Toda escritura autoritativa ocurre en MySQL junto con una '
              'fila de outbox por destino, en la misma transacción; un consumidor por destino proyecta hacia MongoDB, '
              'Elasticsearch, Cassandra, Neo4j, Redis y la copia del catálogo, de forma idempotente y sin que un '
              'destino caído retrase a los demás.'),
        ('t', ['Componente', 'Responsabilidad', 'Usuario del backend'], [
            ['MySQL 8', 'Usuarios, ofertas, precios, inventario, pedidos, pagos, reseñas, fraude, saga y outbox. Única '
             'fuente de verdad; guarda también las copias del plan B', 'tiendaya (usuario propio)'],
            ['MongoDB 7', 'Productos, variantes, esquemas de atributos por categoría, historial de eventos', 'tiendaya_api · rol a medida'],
            ['Redis 7', 'Carritos con expiración, ventas flash (Lua), autocompletado y cola del plan B, cachés de la '
             'búsqueda semántica e historial de vistos', 'tiendaya_api · ACL'],
            ['Elasticsearch 8.15', 'Búsqueda de texto y vector de cada producto (dense_vector int8 HNSW); decide qué '
             'productos y en qué orden; precio y stock se hidratan desde MySQL', 'tiendaya_api · rol'],
            ['Cassandra 4.1', 'Ventas pagadas por producto, oferta, vendedor y semana', '(sin control de acceso)'],
            ['Neo4j 5.26', 'Compras pagadas: «también compraron» y patrones de fraude', 'neo4j'],
            ['Servicio de embeddings', 'Convierte texto en vectores de 768 números (modelo local, sin estado)', '—'],
            ['Pasarela simulada + SQLite', 'Cobro, consulta y reembolso idempotentes por clave', '—'],
        ]),
        ('p', 'El documento docs/05-diagrama-arquitectura.md incluye además tres vistas editables: componentes y '
              'usuarios, flujo de autoridad → proyecciones → respaldos, y el recorrido de los vectores.'),

        # ── 3 ───────────────────────────────────────────────────────────────────
        ('h1', '3. Recomendación y búsqueda semántica'),
        ('h2', '3.1 Problema'),
        ('p', 'Se midió el sistema antes de cambiarlo, con 35 consultas etiquetadas a mano (exactas, con errores o '
              'sinónimos y en lenguaje natural):'),
        ('b', f"La búsqueda de texto no entiende lenguaje natural: «herramienta para hacer agujeros en la pared» no "
              f"encuentra el taladro. En esas consultas, P@5 = {f2(b['texto']['natural']['p5'])} y MRR = "
              f"{f2(b['texto']['natural']['mrr'])}."),
        ('b', '«Quienes compraron también compraron» (Neo4j) no recomienda nada para productos sin ventas.'),
        ('b', f"La similitud por palabras (more_like_this) no encuentra nada para el "
              f"{round((1 - sim['more_like_this']['con_resultados']) * 100)} % de los productos."),
        ('b', 'Las solicitudes de catálogo no detectan duplicados escritos distinto («WH1000XM5» frente a «WH-1000XM5»).'),

        ('h2', '3.2 Decisión (ADR-004)'),
        ('t', ['Alternativa', 'Por qué no / por qué sí'], [
            ['No introducir cambios', 'No cumple el requerimiento y conserva los problemas medidos'],
            ['Extensión relacional (pgvector, MySQL 9 VECTOR)', 'MySQL 8 no tiene tipo vectorial; pgvector exige sumar '
             'PostgreSQL solo para vectores; MySQL 9 comunitario no tiene índice aproximado'],
            ['Base vectorial dedicada (Qdrant, Milvus)', 'Un motor más, un destino más del outbox y una segunda consulta '
             'para combinar con el texto; sin beneficio medible a esta escala (ver 3.7)'],
            ['Redis Stack / MongoDB Atlas Vector Search', 'Exigen cambiar la distribución de motores que ya cumplen otro rol'],
            ['Elasticsearch dense_vector (elegida)', 'Ya está en la arquitectura: kNN con filtros y combinado con el texto '
             'en una sola consulta, con los mismos filtros y facetas'],
        ]),
        ('p', f"Los vectores los calcula un servicio de embeddings propio (FastAPI, puerto 8002) con el modelo "
              f"multilingüe paraphrase-multilingual-mpnet-base-v2 (768 dimensiones), que se ejecuta localmente con "
              f"ONNX. Se comparó con MiniLM-L12 (384 dimensiones): MRR {f2(mod['mpnet (768)']['metricas']['todas']['mrr'])} "
              f"frente a {f2(mod['MiniLM-L12 (384)']['metricas']['todas']['mrr'])}."),

        ('h2', '3.3 Cómo funciona'),
        ('b', 'El vector viaja dentro del documento de búsqueda (mapping v2): dense_vector de 768 dimensiones, '
              'similitud coseno, índice HNSW cuantizado a int8 (cuatro veces menos memoria).'),
        ('b', 'Solo se recalcula si cambia el texto del producto: una huella sha256 de «modelo + texto» permite '
              'reutilizar el vector en los reindexados por precio o stock.'),
        ('b', 'Viaja por el mismo outbox que el resto del documento: no puede quedar un vector de un producto inactivo '
              'ni de otra versión.'),
        ('b', 'Si el servicio no responde, el producto se indexa sin vector y la reconciliación periódica lo completa.'),
        ('b', 'Hallazgo corregido: tras muchas reindexaciones, las versiones borradas de los documentos estorbaban al '
              'grafo HNSW y el kNN llegaba a devolver cero resultados. Se purgan cuando pasan del 20 %.'),

        ('h2', '3.4 Funciones'),
        ('t', ['Función', 'Dónde', 'Cómo y por qué'], [
            ['«También te podría interesar:»', 'Página de producto, debajo de «Las personas que han comprado este '
             'artículo también han comprado estos otros:»', 'kNN del vector del producto; excluye lo que ya muestra la '
             'sección de compras. Las compras sugieren complementos; los vectores, alternativas, y funcionan sin ventas. '
             'Caché de una hora en Redis'],
            ['Búsqueda híbrida', 'Catálogo', 'Texto + kNN en una consulta. Las coincidencias de texto estrictas van '
             'primero; el vector las reordena y agrega relacionados (similitud ≥ 0.45). Sin coincidencias, primero lo '
             'relacionado por significado y después los populares'],
            ['«Te podría interesar»', 'Inicio', 'Una cláusula kNN por semilla (carrito pesa 2; vistos 1, 0.8, 0.64…) '
             'en vez de promediar vectores: el promedio de una laptop y unos audífonos no se parece a ninguno'],
            ['Aviso de duplicados', 'Solicitudes de catálogo (vendedor y administrador)', 'kNN más parecido del nombre; '
             'dos niveles (posible / muy probable); nunca bloquea'],
        ]),

        ('h2', '3.5 Evaluación de calidad'),
        ('p', f"{EVAL['productos']} productos, {len(EVAL['busqueda']['detalle'])} consultas etiquetadas. P@5: relevantes "
              f"entre los 5 primeros; MRR: 1 / posición del primer relevante."),
        ('t', ['Método', 'P@5 (todas)', 'MRR (todas)', 'MRR exactas', 'MRR lenguaje natural'], [
            [nombres[m], f2(b[m]['todas']['p5']), f2(b[m]['todas']['mrr']), f2(b[m]['exacta']['mrr']), f2(b[m]['natural']['mrr'])]
            for m in ('texto', 'vector', 'vector_umbral', 'hibrida')
        ]),
        ('t', ['Productos similares', 'Mismo departamento (P@5)', 'Misma familia (P@5)', 'Productos con resultados'], [
            ['more_like_this (palabras)', f2(sim['more_like_this']['departamento_p5']), f2(sim['more_like_this']['familia_p5']),
             f"{round(sim['more_like_this']['con_resultados'] * 100)} %"],
            ['kNN (vectores)', f2(sim['knn']['departamento_p5']), f2(sim['knn']['familia_p5']),
             f"{round(sim['knn']['con_resultados'] * 100)} %"],
        ]),
        ('b', 'La evaluación cambió una decisión: con la base fija para toda coincidencia de texto, «novela de fantasía» '
              'ponía primero el «Nivel» láser (coincidencia con error). Limitar la base a coincidencias estrictas subió '
              'el MRR de las consultas naturales de 0.61 a 0.67 sin perder nada en las exactas.'),
        ('b', 'El umbral 0.45 es el más bajo con el que ninguna de 6 consultas sin sentido devuelve resultados.'),
        ('b', f"HNSW + int8 coincide en un {round(mod['mpnet (768)']['hnsw_int8']['recall_10'] * 100, 1)} % con la "
              f"búsqueda exacta sobre el catálogo real."),

        ('h2', '3.6 Escala: 100 000 y 1 000 000 de vectores'),
        ('p', 'Vectores sintéticos de 768 dimensiones agrupados alrededor de los productos reales, en un nodo con 512 MB '
              'de heap (una laptop).'),
        ('t', ['Medida', '100k int8', '100k float32', '1M int8'], [
            ['Carga (vectores/s)', str(b100['carga']['docs_por_segundo']), str(b100f['carga']['docs_por_segundo']),
             str(b1m['carga']['docs_por_segundo'])],
            ['Latencia kNN p50 / p95 (cliente)', f"{b100['latencia']['cliente_ms']['p50']} / {b100['latencia']['cliente_ms']['p95']} ms",
             f"{b100f['latencia']['cliente_ms']['p50']} / {b100f['latencia']['cliente_ms']['p95']} ms",
             f"{b1m['latencia']['cliente_ms']['p50']} / {b1m['latencia']['cliente_ms']['p95']} ms"],
            ['Con filtro de categoría (1 %) p50', f"{b100['latencia_filtro_categoria_1pct']['cliente_ms']['p50']} ms",
             f"{b100f['latencia_filtro_categoria_1pct']['cliente_ms']['p50']} ms",
             f"{b1m['latencia_filtro_categoria_1pct']['cliente_ms']['p50']} ms"],
            ['Consultas por segundo (8 hilos)', str(b100['rendimiento']['consultas_por_segundo']),
             str(b100f['rendimiento']['consultas_por_segundo']), str(b1m['rendimiento']['consultas_por_segundo'])],
            ['Memoria del kNN (estimada)', f"{b100['espacio']['memoria_knn_estimada_mb']:.0f} MB",
             f"{b100f['espacio']['memoria_knn_estimada_mb']:.0f} MB", f"{b1m['espacio']['memoria_knn_estimada_mb']:.0f} MB"],
            ['Recall@10 (200 candidatos)', f2(b100['recall_10']['200']), f2(b100f['recall_10']['200']), f2(b1m['recall_10']['200'])],
            ['Recall@10 con reordenamiento float32', f2(b100['reordenado_float32']['200']['recall_10']), '—',
             f2(b1m['reordenado_float32']['200']['recall_10'])],
            ['Búsqueda exacta sin HNSW', f"{b100['exacta_sin_hnsw']['p50_ms']:.0f} ms", f"{b100f['exacta_sin_hnsw']['p50_ms']:.0f} ms",
             f"{b1m['exacta_sin_hnsw']['p50_ms']:.0f} ms"],
        ]),
        ('b', 'La latencia casi no cambia de 100 000 a 1 000 000 (HNSW crece de forma logarítmica); sin HNSW, la búsqueda '
              'exacta crece de forma lineal (1.5 s proyectados con 10 M).'),
        ('b', 'int8 pierde exactitud en familias de productos muy parecidas; pedir 5 veces más vecinos y reordenarlos '
              'con los vectores float32 recupera un recall de 0.99 por unos 13 ms.'),
        ('b', 'Límites encontrados: con 512 MB de heap, fusionar 1 M de vectores en un segmento hizo caer el nodo por '
              'falta de memoria, y el 70 % del disco es el vector guardado como texto en _source.'),

        ('h2', '3.7 Cuándo migrar a una base vectorial dedicada'),
        ('p', 'Una base vectorial dedicada no es más rápida por sí misma: Elasticsearch ya responde en ~9 ms con un millón '
              'de vectores. Su beneficio aparece cuando la carga vectorial compite con la búsqueda de texto o cuando la '
              'memoria encarece el clúster. Condiciones, con los números medidos:'),
        ('t', ['Condición', 'Umbral', 'Por qué'], [
            ['Memoria de los vectores', '~900 bytes por vector con int8: 10 M ≈ 8.6 GB; 50 M ≈ 43 GB por copia',
             'Si no caben en la caché de páginas, el kNN lee de disco'],
            ['Tráfico semántico sostenido', '> ~300 consultas kNN por segundo por nodo (medido: 556 con 100k, 328 con 1M)',
             'Le quita CPU y caché a la búsqueda de texto'],
            ['Ritmo de escritura', '> ~1 600 vectores/s por nodo, o reindexar decenas de millones al cambiar de modelo',
             'Bloquearía la indexación de cambios normales'],
            ['Mantenimiento', 'Fusionar 1 M de vectores no cupo en 512 MB de heap', 'Reconstruir el grafo exige memoria'],
            ['Funciones', 'Varios vectores por producto, colecciones por vendedor', 'Las bases dedicadas están hechas para eso'],
        ]),
        ('p', 'El primer paso sería separar los vectores en nodos propios de Elasticsearch (la misma tecnología); la '
              'arquitectura ya lo permite, porque el outbox tiene un destino por componente. Con 69 productos, y aun '
              'con un millón, no se cumple ninguna condición.'),

        ('h2', '3.8 Si algo falla'),
        ('t', ['Falla', 'Qué pasa'], [
            ['Servicio de embeddings', 'Las consultas ya hechas usan su vector guardado en Redis; las nuevas, solo texto. '
             'Similares e inicio siguen (usan vectores ya indexados). Duplicados: sin aviso'],
            ['Elasticsearch', 'Similares → más vendidos de la categoría; búsqueda → MongoDB y plan B; inicio → sin sección'],
            ['Redis', 'Sin cachés: se consulta directo'],
        ]),

        # ── 4 ───────────────────────────────────────────────────────────────────
        ('h1', '4. Control de acceso'),
        ('h2', '4.1 Problema'),
        ('p', 'Antes de esta entrega Redis no pedía autenticación, el backend se conectaba a MongoDB como root, '
              'Elasticsearch tenía la seguridad desactivada y las contraseñas estaban fijas en el repositorio. Un fallo '
              'en el backend o cualquier proceso de la máquina tenía control total sobre los tres motores.'),
        ('h2', '4.2 Decisión (ADR-005)'),
        ('t', ['Alternativa', 'Resultado'], [
            ['No cambiar', 'No cumple'],
            ['Solo aislar la red', 'Cualquier proceso local sigue con control total; el backend sigue siendo root'],
            ['Una contraseña por motor', 'Autenticación sin autorización: un fallo del backend puede seguir borrando todo'],
            ['Usuarios por servicio con mínimo privilegio (elegida)', 'Autenticación y autorización acotada por servicio'],
            ['Gestor de secretos externo', 'Un servicio más; cambia dónde viven las contraseñas, no los permisos'],
        ]),
        ('h2', '4.3 Usuarios y permisos'),
        ('t', ['Motor', 'Backend', 'Herramientas de consulta', 'Instalación / operación'], [
            ['Redis (ACL)', 'tiendaya_api: 9 prefijos de llaves y 34 comandos; sin KEYS, FLUSHALL, CONFIG, ACL ni INFO',
             'tiendaya_lectura y default: solo lectura (Redis Commander)', 'tiendaya_admin'],
            ['MongoDB (roles)', 'tiendaya_api: rol a medida sobre 5 colecciones (find, insert, update, remove, createIndex, '
             'listIndexes); sin drop ni otras bases', 'tiendaya_lectura: read (Mongo Express)', 'tiendaya_admin: dbOwner solo de tiendaya'],
            ['Elasticsearch (roles)', 'tiendaya_api: documentos de productos*; no crea ni borra índices ni mueve el alias',
             'tiendaya_lectura: solo leer (Elasticvue)', 'tiendaya_indexador: productos* y bench_vectores_*'],
        ]),
        ('b', 'Reglas versionadas en el repositorio (database/redis/acl.conf, database/mongo/03_usuarios.js, '
              'database/elasticsearch/seguridad.json); contraseñas generadas al azar en .env, fuera de git.'),
        ('b', 'Sin modo abierto: si falta una contraseña, docker compose se niega a arrancar y dice qué ejecutar.'),
        ('b', 'Las instalaciones existentes adoptan las contraseñas con que se crearon sus volúmenes; un solo comando '
              '(configurar-acceso.ps1) configura un equipo, y otro el entorno DEMO de la presentación.'),
        ('h2', '4.4 Validación'),
        ('p', 'Los permisos salen de un inventario de lo que el código hace y se validaron corriendo toda la suite con los '
              'usuarios restringidos y revisando los rechazos de cada motor (ACL LOG de Redis, registro de control de '
              'acceso de MongoDB, advertencias del backend con Elasticsearch). El plan B podía esconder un permiso '
              'faltante —si un motor rechaza, el backend usa el respaldo sin que falle ninguna prueba—; así apareció '
              'ZRANGEBYLEX en Redis, que el inventario no tenía.'),
        ('h2', '4.5 Evidencia'),
        ('t', ['Intento', 'Resultado'], [
            ['Conectarse sin credenciales (Redis, MongoDB, Elasticsearch)', 'NOAUTH · requires authentication · 401'],
            ['Backend escribe una llave fuera de sus prefijos en Redis', 'NOPERM No permissions to access a key'],
            ['Backend ejecuta FLUSHALL, KEYS, CONFIG o ACL en Redis', 'NOPERM ... has no permissions to run the command'],
            ['Script Lua del backend escribe fuera de sus prefijos', 'ACL failure in script'],
            ['Backend lee migraciones, admin.system.users o crea un usuario root en MongoDB', 'not authorized'],
            ['Backend crea un índice, mueve el alias o crea un superusuario en Elasticsearch', '403 security_exception'],
            ['Usuarios de lectura escriben o borran', 'NOPERM · not authorized · 403'],
        ]),
        ('p', 'backend/scripts/verificar_permisos.py hace 40 intentos reales contra el sistema en marcha (40 de 40 '
              'dieron lo esperado) y deja la tabla en docs/evidencia/permisos.md; además hay 50 pruebas automáticas. '
              'Lo destructivo no se ejecuta: se pregunta al motor si el usuario tendría el privilegio '
              '(connectionStatus, has_privileges).'),
        ('h2', '4.6 Limitaciones asumidas'),
        ('b', 'Sin TLS en desarrollo (motores en la misma máquina); en producción se activaría sin cambiar usuarios ni roles.'),
        ('b', 'Los superusuarios siguen existiendo, solo para crear los usuarios; nunca los usa el backend.'),
        ('b', 'Neo4j y Cassandra no se restringieron en esta entrega (MySQL ya usaba un usuario propio).'),

        # ── 5 ───────────────────────────────────────────────────────────────────
        ('h1', '5. Retrospectiva'),
        ('p', 'Resumen de docs/49-retrospectiva.md: catorce decisiones de las cuatro entregas, evaluadas con los criterios '
              'de los ADR y evidencia medida en el proyecto.'),
        ('t', ['Decisión', 'Veredicto', 'Justificación'], [
            ['MySQL única autoridad; el resto, proyecciones', 'Se sostiene', 'Toda divergencia se corrigió reproyectando '
             'desde MySQL; invariantes I1–I7 en cada fase'],
            ['MongoDB para el contenido del catálogo', 'Se sostiene', 'Atributos distintos por categoría, variantes e '
             'historial sin tablas EAV'],
            ['Redis para carritos y ventas flash', 'Se sostiene', 'TTL nativo y Lua atómico; el ACL aplica dentro de Lua'],
            ['Elasticsearch para búsqueda y vectores', 'Se sostiene', '6/17 → 17/17 aciertos; híbrida MRR 0.62 → 0.82; ~9 ms con 1 M'],
            ['Checkout como saga', 'Se sostiene', 'Escenarios de falla E00–E17 sin dinero ni inventario perdidos'],
            ['Outbox por destino (segunda versión)', 'Se sostiene', 'La primera aplicaba deltas: Mongo quedó con stock 9 frente '
             'a 16. Una proyección se deriva del estado'],
            ['Precio y stock copiados en MongoDB', 'Se replantea', 'Cuatro copias del mismo dato; ahí ocurrió la falla más visible'],
            ['Escribir el catálogo en MongoDB y después en MySQL', 'Se replantea', 'Escritura doble con ventana de 10 minutos'],
            ['Neo4j sin reconciliación propia', 'Se replantea', 'La divergencia 192/175 persistió toda la entrega'],
            ['Cassandra desde la Entrega 2', 'Se replantea el momento', 'A este volumen bastaban tablas resumen en MySQL'],
            ['Seguridad al final del proyecto', 'Se replantea', 'Tocar decenas de archivos y adoptar contraseñas antiguas'],
            ['Plan B con respaldo para cada motor', 'Se replantea el alcance', 'Escondió un permiso faltante sin fallar ninguna prueba'],
            ['Un nodo por motor con memoria mínima', 'Se replantea', 'Caída por memoria con 1 M de vectores; kNN vacío por borrados'],
        ]),
        ('p', 'La regla que más valor dio y que se mantendría por encima de todo: una sola autoridad por dato, y todo lo '
              'demás, proyecciones que se pueden reconstruir.'),

        # ── 6 ───────────────────────────────────────────────────────────────────
        ('h1', '6. Verificación y presentación'),
        ('b', 'Suite de integración del backend contra los motores reales (sin mocks): 396 pruebas pasan; quedan 3 fallas '
              'anteriores a esta entrega (checkout de venta flash y dos de bodegas, introducidas por un cambio de '
              'inventario) que se documentan como deuda.'),
        ('b', 'Invariantes de consistencia I1–I7: se cumplen al cierre de cada fase.'),
        ('b', '56 pruebas de vectores, 50 de permisos y los scripts de evidencia (evaluar_vectores, benchmark_vectores, '
              'verificar_permisos) que se pueden volver a ejecutar.'),
        ('b', 'Entorno DEMO de la presentación actualizado: control de acceso en Redis, MongoDB y Elasticsearch, índice '
              'v2 con los vectores de sus 106 productos y el servicio de embeddings dentro del modo presentación '
              '(start-presentation.ps1 / stop-presentation.ps1). Verificado: los siete motores en «ok», búsqueda híbrida, '
              'similares e inicio funcionando sobre los datos DEMO.'),

        # ── 7 ───────────────────────────────────────────────────────────────────
        ('h1', '7. Conclusiones'),
        ('b', 'La recomendación semántica se resolvió sin un motor nuevo: el vector vive en el índice de búsqueda que ya '
              'existía, se combina con el texto en una sola consulta y mejora la búsqueda (MRR 0.62 → 0.82) además de '
              'habilitar tres funciones nuevas.'),
        ('b', 'La pregunta de si una base vectorial dedicada vale la pena quedó respondida con números: no a esta escala '
              'ni con un millón de productos; sí cuando la memoria de los vectores o su tráfico compitan con la búsqueda '
              'de texto, y el camino para llegar ahí ya existe.'),
        ('b', 'El control de acceso cubre los tres motores NoSQL que usa el backend, con mínimo privilegio por servicio, '
              'sin contraseñas en el repositorio y con evidencia que se regenera.'),
        ('b', 'La retrospectiva identifica con honestidad qué se haría distinto —copias de precio en MongoDB, escritura '
              'doble del catálogo, sincronización de Neo4j, Cassandra prematura, seguridad tardía— y por qué.'),

        # ── Anexo ───────────────────────────────────────────────────────────────
        ('h1', 'Anexo. Documentos y comandos'),
        ('t', ['Documento', 'Contenido'], [
            ['docs/05-diagrama-arquitectura.md', 'Arquitectura final (diagrama y vistas)'],
            ['docs/45-ADR-004-busqueda-vectorial.md', 'Decisión del componente vectorial'],
            ['docs/46-vectores-implementacion.md', 'Implementación de los vectores'],
            ['docs/evidencia/evaluacion-vectores.md', 'Evaluación de calidad'],
            ['docs/evidencia/escala-vectores.md', 'Benchmark de escala'],
            ['docs/47-control-de-acceso.md', 'Control de acceso por motor'],
            ['docs/48-ADR-005-control-de-acceso.md', 'Decisión del control de acceso'],
            ['docs/evidencia/permisos.md', 'Evidencia de permisos'],
            ['docs/49-retrospectiva.md', 'Retrospectiva'],
        ]),
        ('t', ['Comando', 'Para qué'], [
            ['scripts\\setup.ps1', 'Instalación desde cero (incluye el control de acceso)'],
            ['scripts\\configurar-acceso.ps1', 'Control de acceso en un equipo ya instalado'],
            ['scripts\\configurar-acceso-demo.ps1 y scripts\\migrar-indice-demo.ps1', 'DEMO: control de acceso e índice con vectores'],
            ['scripts\\start-presentation.ps1 / stop-presentation.ps1', 'Modo presentación'],
            ['backend\\scripts\\verificar_permisos.py', 'Evidencia del control de acceso'],
            ['backend\\scripts\\evaluar_vectores.py', 'Evaluación de calidad'],
        ]),
    ]


# ══ Word ══════════════════════════════════════════════════════════════════════

def _sombra(celda, hex6: str) -> None:
    tcPr = celda._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex6)
    tcPr.append(shd)


def _anchos(encabezados: list[str], filas: list[list], total: float = 6.5) -> list[float]:
    """Ancho de cada columna: un mínimo para que ninguna palabra (ni el encabezado) se parta, y el
    resto repartido en proporción a cuánto texto lleva."""
    minimos, pesos = [], []
    for i, encabezado in enumerate(encabezados):
        textos = [str(f[i]) for f in filas]
        palabra_mas_larga = max([len(p) for t in textos for p in t.split()] + [len(encabezado)])
        minimos.append(palabra_mas_larga * 0.085 + 0.22)  # ~0.085" por carácter a 9.5 pt + márgenes
        pesos.append(min(sum(len(t) for t in textos) / max(len(textos), 1), 90))
    sobrante = max(total - sum(minimos), 0)
    return [m + sobrante * p / sum(pesos) for m, p in zip(minimos, pesos)]


def _margenes_celda(tabla) -> None:
    """Margen interno de las celdas para que el texto no toque los bordes."""
    tblPr = tabla._tbl.tblPr
    margenes = OxmlElement('w:tblCellMar')
    for lado, valor in (('top', 40), ('bottom', 40), ('left', 90), ('right', 90)):
        elemento = OxmlElement(f'w:{lado}')
        elemento.set(qn('w:w'), str(valor))
        elemento.set(qn('w:type'), 'dxa')
        margenes.append(elemento)
    tblPr.append(margenes)


def _estilo(run, size: float, bold: bool = False, italic: bool = False, font: str = FONT_BODY) -> None:
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = NEGRO
    run._element.rPr.rFonts.set(qn('w:eastAsia'), font)


def _campo(parrafo, instruccion: str) -> None:
    """Inserta un campo de Word (PAGE, TOC…) que Word calcula al abrir o actualizar."""
    for tipo, texto in (('begin', None), (None, instruccion), ('separate', None), (None, ''), ('end', None)):
        run = parrafo.add_run()
        if tipo:
            fld = OxmlElement('w:fldChar')
            fld.set(qn('w:fldCharType'), tipo)
            run._r.append(fld)
        elif texto is not None and texto:
            instr = OxmlElement('w:instrText')
            instr.set(qn('xml:space'), 'preserve')
            instr.text = texto
            run._r.append(instr)


def _portada(doc: Document) -> None:
    doc.add_paragraph().paragraph_format.space_before = Pt(60)
    for texto, size, bold in (('TiendaYa', 28, True), ('Informe de arquitectura final — Entrega final', 16, False),
                              ('Bases de Datos 2', 13, True)):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(8)
        _estilo(p.add_run(texto), size, bold=bold, font=FONT_HEADING if size > 13 else FONT_BODY)
    doc.add_paragraph().paragraph_format.space_before = Pt(60)
    for linea in ('Barrios Cruz, Mynor Enrique', 'Universidad del Istmo — UNIS', 'Guatemala, 30 de octubre de 2026'):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p.paragraph_format.space_after = Pt(6)
        _estilo(p.add_run(linea), 11)
    doc.add_page_break()


def _indice(doc: Document) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(14)
    _estilo(p.add_run('Índice'), 16, bold=True, font=FONT_HEADING)
    _campo(doc.add_paragraph(), 'TOC \\o "1-2" \\h \\z \\u')
    doc.add_page_break()


def construir_docx() -> None:
    doc = Document()
    for seccion in doc.sections:
        seccion.top_margin = seccion.bottom_margin = seccion.left_margin = seccion.right_margin = Inches(1)
        pie = seccion.footer.paragraphs[0]
        pie.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _campo(pie, 'PAGE')
    normal = doc.styles['Normal']
    normal.font.name = FONT_BODY
    normal.font.size = Pt(11)

    _portada(doc)
    _indice(doc)
    for bloque in contenido():
        tipo = bloque[0]
        if tipo in ('h1', 'h2', 'h3'):
            nivel = int(tipo[1])
            p = doc.add_heading(bloque[1], level=nivel)
            p.paragraph_format.space_before = Pt({1: 16, 2: 12, 3: 10}[nivel])
            p.paragraph_format.space_after = Pt({1: 8, 2: 6, 3: 5}[nivel])
            for run in p.runs:
                _estilo(run, {1: 14, 2: 12, 3: 11}[nivel], bold=True, italic=nivel == 3, font=FONT_HEADING)
        elif tipo == 'p':
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(8)
            _estilo(p.add_run(bloque[1]), 11)
        elif tipo == 'b':
            p = doc.add_paragraph(style='List Bullet')
            p.paragraph_format.space_after = Pt(3)
            _estilo(p.add_run(bloque[1]), 11)
        elif tipo == 't':
            encabezados, filas = bloque[1], bloque[2]
            tabla = doc.add_table(rows=1, cols=len(encabezados))
            tabla.style = 'Table Grid'
            tabla.alignment = WD_TABLE_ALIGNMENT.CENTER
            tabla.autofit = False
            _margenes_celda(tabla)
            for celda, texto in zip(tabla.rows[0].cells, encabezados):
                _sombra(celda, 'D9D9D9')
                celda.paragraphs[0].text = ''
                _estilo(celda.paragraphs[0].add_run(texto), 9.5, bold=True)
            for fila in filas:
                celdas = tabla.add_row().cells
                for celda, texto in zip(celdas, fila):
                    _estilo(celda.paragraphs[0].add_run(str(texto)), 9.5)
            anchos = _anchos(encabezados, filas)
            for fila in tabla.rows:
                for celda, ancho in zip(fila.cells, anchos):
                    celda.width = Inches(ancho)
            doc.add_paragraph().paragraph_format.space_after = Pt(6)
        elif tipo == 'img':
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run().add_picture(str(bloque[1]), width=Inches(bloque[2]))
    SALIDA.mkdir(parents=True, exist_ok=True)
    doc.save(DOCX_OUT)
    print('DOCX:', DOCX_OUT.relative_to(RAIZ))


def exportar_pdf() -> None:
    """Word actualiza el índice y los números de página y exporta el PDF."""
    script = f'''
$ErrorActionPreference = 'Stop'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {{
    $doc = $word.Documents.Open('{DOCX_OUT}')
    foreach ($toc in $doc.TablesOfContents) {{ $toc.Update() }}
    $doc.Fields.Update() | Out-Null
    $doc.Save()
    $doc.ExportAsFixedFormat('{PDF_OUT}', 17)
    $doc.Close()
}} finally {{ $word.Quit() }}
'''
    subprocess.run(['powershell', '-NoProfile', '-Command', script], check=True)
    print('PDF: ', PDF_OUT.relative_to(RAIZ))


# ══ Markdown ═══════════════════════════════════════════════════════════════════

def construir_md() -> None:
    lineas = ['# Informe de arquitectura final — TiendaYa (Entrega final)', '',
              'Versión Word y PDF: [`docs/informe/`](informe/). Generado por `docs/informe/generar_informe_entrega4.py`; '
              'las cifras se leen de `docs/evidencia/`.', '']
    for bloque in contenido():
        tipo = bloque[0]
        if tipo in ('h1', 'h2', 'h3'):
            lineas += ['#' * (int(tipo[1]) + 1) + ' ' + bloque[1], '']
        elif tipo == 'p':
            lineas += [bloque[1], '']
        elif tipo == 'b':
            lineas.append('- ' + bloque[1])
        elif tipo == 't':
            if lineas and lineas[-1].startswith('- '):
                lineas.append('')
            lineas.append('| ' + ' | '.join(bloque[1]) + ' |')
            lineas.append('|' + '---|' * len(bloque[1]))
            lineas += ['| ' + ' | '.join(str(c).replace('|', '\\|') for c in fila) + ' |' for fila in bloque[2]]
            lineas.append('')
        elif tipo == 'img':
            lineas += [f'![Arquitectura final]({Path(bloque[1]).relative_to(DOCS).as_posix()})', '']
        if tipo != 'b' and lineas and lineas[-1].startswith('- '):
            lineas.append('')
    texto = '\n'.join(lineas)
    # Una lista seguida de un encabezado o párrafo necesita una línea en blanco.
    texto = texto.replace('\n#', '\n\n#').replace('\n\n\n', '\n\n')
    MD_OUT.write_text(texto.rstrip() + '\n', encoding='utf-8')
    print('MD:  ', MD_OUT.relative_to(RAIZ))


if __name__ == '__main__':
    construir_docx()
    exportar_pdf()
    construir_md()
