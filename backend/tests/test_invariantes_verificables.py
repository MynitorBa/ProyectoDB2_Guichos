"""Un invariante que no se pudo revisar completo queda «no verificable», nunca cumplido.

I6 recorre todo el libro de la pasarela por páginas (antes miraba solo los
1 000 cobros más recientes) e I7 distingue cuando Elasticsearch no respondió.
"""

from uuid import uuid4

import httpx
import pytest

from app.core.db_elastic import get_es
from app.core.db_mongo import get_mongo_db
from app.services import consistency_service
from tests.conftest import URL_PASARELA
from tests.test_checkout import TestSession


def _cobro_sin_pedido() -> str:
    """Un cargo aprobado cuya clave no existe en MySQL: siempre es una violación de I6."""
    clave = f'auditoria-{uuid4()}'
    httpx.post(f'{URL_PASARELA}/cobros', json={'monto': '1.00'}, headers={'Idempotency-Key': clave},
               timeout=5).raise_for_status()
    return clave


@pytest.fixture
def cobro_antiguo(pasarela_en_modo):
    """Un cargo discrepante seguido de cobros más recientes que lo empujan fuera de la primera página."""
    pasarela_en_modo('aprobar')
    antiguo = _cobro_sin_pedido()
    for _ in range(3):
        _cobro_sin_pedido()
    return antiguo


def test_i6_encuentra_un_cobro_discrepante_aunque_no_este_en_la_primera_pagina(cobro_antiguo, monkeypatch):
    monkeypatch.setattr(consistency_service, 'PAGINA_COBROS', 2)
    with TestSession() as db:
        resultado = consistency_service.pasarela_coincide(db, {cobro_antiguo})

    assert resultado['ok'] is False
    assert resultado['ejemplos'] == [{'clave': cobro_antiguo, 'cobro': 'aprobado', 'pedido': None}]


def test_i6_truncado_queda_no_verificable_y_no_cumplido(cobro_antiguo, monkeypatch):
    monkeypatch.setattr(consistency_service, 'PAGINA_COBROS', 1)
    monkeypatch.setattr(consistency_service, 'MAX_PAGINAS_COBROS', 1)
    with TestSession() as db:
        resultado = consistency_service.pasarela_coincide(db, {cobro_antiguo})

    # El cargo discrepante quedó fuera de lo revisado: no puede reportarse como cumplido.
    assert resultado['ok'] is None
    assert 'Incompleto' in resultado['detalle']


class _ElasticsearchCaido:
    def mget(self, **kwargs):
        raise ConnectionError('Elasticsearch no responde')


def test_i7_sin_elasticsearch_queda_no_verificable():
    with TestSession() as db:
        resultado = consistency_service.proyecciones_convergen(db, get_mongo_db(), _ElasticsearchCaido())

    assert resultado['ok'] in (None, False)          # nunca True sin revisar Elasticsearch
    if resultado['ok'] is None:
        assert 'Elasticsearch no respondió' in resultado['detalle']


def test_i7_con_elasticsearch_puede_cumplirse():
    with TestSession() as db:
        resultado = consistency_service.proyecciones_convergen(db, get_mongo_db(), get_es())

    assert 'Elasticsearch no respondió' not in resultado['detalle']


def test_el_resumen_no_cuenta_lo_no_verificable_como_cumplido(monkeypatch):
    monkeypatch.setattr(consistency_service, 'pasarela_coincide',
                        lambda db, claves=None: {'id': 'I6', 'titulo': 'I6', 'ok': None, 'violaciones': 0,
                                                 'ejemplos': [], 'detalle': 'No verificable'})
    with TestSession() as db:
        resultado = consistency_service.verificar(db, get_mongo_db(), get_es())

    assert resultado['ok'] is False
    assert 'I6' in resultado['no_verificables']


class _Respuesta:
    def __init__(self, datos):
        self._datos = datos

    def json(self):
        return self._datos


@pytest.mark.parametrize('base, ledger_ajeno', [('tiendaya', 'ledger.demo.db'), ('tiendaya_demo', 'ledger.db')])
def test_i6_rechaza_comparar_una_base_con_el_ledger_del_otro_entorno(monkeypatch, base, ledger_ajeno):
    get_real = consistency_service.httpx.get

    def get(url, **kwargs):
        if url.endswith('/control'):
            return _Respuesta({'modo': 'aprobar', 'ledger': ledger_ajeno})
        return get_real(url, **kwargs)
    monkeypatch.setattr(consistency_service.httpx, 'get', get)
    monkeypatch.setattr(consistency_service.settings, 'MYSQL_DB', base)
    with TestSession() as db:
        resultado = consistency_service.pasarela_coincide(db)

    assert resultado['ok'] is None
    assert 'configuración inválida' in resultado['detalle'] and ledger_ajeno in resultado['detalle']


def test_la_pasarela_informa_su_ledger():
    # La de las pruebas usa un ledger temporal propio: ni el principal ni el de la DEMO.
    ledger = httpx.get(f'{URL_PASARELA}/control', timeout=5).json()['ledger']
    assert ledger.startswith('pasarela_pruebas_')


# ── Candado de la suite (auditoría H-02) ──────────────────────────────────────

def test_la_configuracion_de_pruebas_no_apunta_a_la_demo():
    from tests.conftest import senales_de_demo
    assert senales_de_demo() == []


def test_la_suite_se_niega_a_correr_contra_la_demo():
    """Una corrida real de pytest con MySQL de la DEMO termina antes de ejecutar cualquier prueba."""
    import os
    import subprocess
    import sys
    entorno = {**os.environ, 'MYSQL_DB': 'tiendaya_demo', 'MYSQL_PORT': '3317'}
    corrida = subprocess.run(
        [sys.executable, '-m', 'pytest', 'tests/test_salud.py', '-q', '-p', 'no:cacheprovider'],
        cwd=os.path.dirname(os.path.dirname(__file__)), env=entorno, capture_output=True, text=True, timeout=120,
    )
    assert corrida.returncode == 2
    assert 'no se ejecutan contra la DEMO' in corrida.stdout + corrida.stderr
    assert 'MySQL' in corrida.stdout + corrida.stderr and 'passed' not in corrida.stdout
