"""Servicio de embeddings (Entrega 4) y su cliente en el backend."""

import httpx
import numpy as np

from app.core import salud
from app.core.config import settings
from app.services import embeddings_client as emb


def _http():
    return httpx.Client(base_url=settings.EMBEDDINGS_URL, timeout=30)


def test_health_informa_el_modelo_y_sus_dimensiones():
    estado = emb.estado()
    assert estado['listo'] is True
    assert estado['dimensiones'] > 0
    assert 'multilingual' in estado['modelo']


def test_los_vectores_salen_normalizados_y_en_orden():
    textos = ['Audífonos inalámbricos con cancelación de ruido', 'Taladro percutor de 20 V']
    vectores = emb.generar(textos)
    assert len(vectores) == 2
    assert all(abs(np.linalg.norm(v) - 1) < 1e-3 for v in vectores)
    # El orden importa: el mismo texto da el mismo vector.
    assert np.allclose(emb.generar([textos[1]])[0], vectores[1], atol=1e-4)


def test_textos_con_el_mismo_significado_quedan_mas_cerca():
    audifonos, bluetooth, taladro = np.array(emb.generar([
        'Audífonos inalámbricos Sony con cancelación de ruido',
        'auriculares bluetooth para escuchar música sin cables',
        'Taladro percutor DeWalt 20V',
    ]))
    assert audifonos @ bluetooth > audifonos @ taladro


def test_lotes_mas_grandes_que_el_limite_se_parten():
    vectores = emb.generar([f'Producto de prueba {i}' for i in range(70)])
    assert len(vectores) == 70


def test_el_servicio_rechaza_solicitudes_invalidas():
    with _http() as http:
        assert http.post('/embeddings', json={'textos': []}).status_code == 422
        assert http.post('/embeddings', json={'textos': ['x'] * 65}).status_code == 422


def test_sin_servicio_el_cliente_devuelve_none_y_abre_el_circuito():
    caido = httpx.Client(base_url='http://127.0.0.1:1', timeout=0.5)
    assert emb.generar(['algo'], http=caido) is None
    assert not salud.disponible('embeddings')
    # Con el circuito abierto ni siquiera lo intenta.
    assert emb.generar(['algo']) is None


def test_el_texto_del_producto_reune_nombre_categoria_descripcion_y_atributos():
    texto = emb.texto_producto({
        'nombre': 'Laptop Dell Inspiron 15',
        'categoria': {'slug': 'computadoras', 'nombre': 'Computadoras'},
        'descripcion': 'Ideal para trabajo y estudio.',
        'atributos': {'ram': '16 GB', 'color': None},
    })
    assert texto == ('Laptop Dell Inspiron 15. Categoría: Computadoras. '
                     'Ideal para trabajo y estudio. ram: 16 GB')
