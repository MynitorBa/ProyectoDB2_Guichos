"""Posibles duplicados al proponer un producto nuevo (Entrega 4).

Cuando un vendedor propone un producto, su texto (nombre, categorías,
descripción y atributos) se convierte en vector igual que los productos del
índice y se buscan los más cercanos. Así se detecta «Audifonos Sony WH1000XM5»
aunque en el catálogo se llame «Audífonos Sony WH-1000XM5».

Es un **aviso, nunca un bloqueo**: el vendedor puede preferir ofrecer el
producto existente y el administrador decide al revisar. Los umbrales se
midieron con el catálogo real (docs/evidencia/linea-base-entrega4.md): el mismo
producto escrito distinto da 0.82–0.96; uno de la misma familia pero distinto
llega a 0.79, y a veces más (otra laptop frente a la Dell: 0.835). Por eso hay
dos niveles y no se descarta nada automáticamente.

Además del vector se compara el nombre: el mayor entre la proporción de
palabras en común y el parecido letra por letra del nombre sin espacios ni
signos («WH1000XM5» = «WH-1000XM5»). El vector del producto incluye su
descripción completa, así que una propuesta con solo el nombre queda por
debajo de 0.80 aunque sea idéntico; la comparación de nombres la detecta. En
productos de la misma familia no llega al umbral (Galaxy S23 Ultra frente a
Galaxy A54: 0.76; HP Envy 13 frente a HP Pavilion 14: 0.62).

Si el servicio de embeddings o Elasticsearch no responden, no hay aviso: la
solicitud sigue su curso normal.
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher

from elastic_transport import TransportError
from elasticsearch import ApiError, Elasticsearch

from app.core import salud
from app.core.config import settings
from app.services import embeddings_client, search_index_service
from app.services.search_service import normalizar

logger = logging.getLogger(__name__)

UMBRAL_POSIBLE = 0.80
UMBRAL_MUY_PROBABLE = 0.90
NOMBRE_POSIBLE = 0.80
NOMBRE_MUY_PROBABLE = 0.95
# Vecinos que se revisan: incluye los que solo coinciden por nombre.
SIMILITUD_MINIMA_CANDIDATO = 0.6
MAX_DUPLICADOS = 3
CANDIDATOS_KNN = 100


def parecido_nombres(a: str, b: str) -> float:
    """Parecido de dos nombres (0 a 1), sin tildes ni signos.

    El mayor entre las palabras en común (sirve si cambia el orden) y el
    parecido letra por letra sin espacios (sirve si cambian guiones o espacios).
    """
    palabras_a = set(re.findall(r'\w+', normalizar(a)))
    palabras_b = set(re.findall(r'\w+', normalizar(b)))
    if not palabras_a or not palabras_b:
        return 0.0
    en_comun = len(palabras_a & palabras_b) / len(palabras_a | palabras_b)
    compacto = SequenceMatcher(None, re.sub(r'\W+', '', normalizar(a)), re.sub(r'\W+', '', normalizar(b))).ratio()
    return max(en_comun, compacto)


def texto_propuesta(nombre: str, descripcion: str | None, categorias: list[str], atributos: dict | None) -> str:
    """El mismo texto que se vectoriza para un producto del índice."""
    return search_index_service.texto_vector({
        'nombre': nombre,
        'descripcion': descripcion or '',
        'categorias': [{'nombre': c} for c in categorias],
        'texto_atributos': ' '.join(str(v) for v in (atributos or {}).values() if isinstance(v, str)),
    })


def posibles_duplicados(
    es: Elasticsearch, *, nombre: str, descripcion: str | None = None,
    categorias: list[str] | None = None, atributos: dict | None = None,
) -> list[dict]:
    """``[{producto_ref, nombre, sku, similitud, parecido_nombre, nivel}]``, lo más probable primero."""
    if not (nombre or '').strip() or not salud.disponible('elasticsearch'):
        return []
    vectores = embeddings_client.generar([texto_propuesta(nombre, descripcion, categorias or [], atributos)])
    if not vectores:
        return []
    try:
        respuesta = es.search(
            index=settings.ES_INDEX_ALIAS, size=10, source=['nombre', 'sku'],
            knn={
                'field': 'vector', 'query_vector': vectores[0], 'k': 10,
                'num_candidates': CANDIDATOS_KNN, 'similarity': SIMILITUD_MINIMA_CANDIDATO,
                'filter': {'term': {'estado': 'activo'}},
            },
        )
    except (TransportError, ApiError) as exc:
        if isinstance(exc, TransportError):
            salud.registrar_falla('elasticsearch', exc)
        logger.warning('No se pudieron buscar duplicados de «%s»: %s', nombre, exc)
        return []
    salud.registrar_exito('elasticsearch')
    resultado = []
    for hit in respuesta['hits']['hits']:
        # Con similitud coseno, Elasticsearch da _score = (1 + coseno) / 2.
        similitud = round(2 * hit['_score'] - 1, 3)
        nombre_candidato = hit['_source'].get('nombre') or ''
        palabras = round(parecido_nombres(nombre, nombre_candidato), 3)
        if similitud >= UMBRAL_MUY_PROBABLE or palabras >= NOMBRE_MUY_PROBABLE:
            nivel = 'muy_probable'
        elif similitud >= UMBRAL_POSIBLE or palabras >= NOMBRE_POSIBLE:
            nivel = 'posible'
        else:
            continue
        resultado.append({
            'producto_ref': hit['_id'], 'nombre': nombre_candidato, 'sku': hit['_source'].get('sku'),
            'similitud': similitud, 'parecido_nombre': palabras, 'nivel': nivel,
        })
    resultado.sort(key=lambda d: (d['nivel'] != 'muy_probable', -max(d['similitud'], d['parecido_nombre'])))
    return resultado[:MAX_DUPLICADOS]
