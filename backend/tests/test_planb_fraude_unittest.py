"""Regresión F04 sin grafo; ejecución directa sin fixtures de bases reales."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.v1.reviews import fraude_indicador_paginado
from app.services import fraud_detection_service as fraud


class FraudeSinGrafoTests(unittest.TestCase):
    def call_rule(self, regla):
        return fraude_indicador_paginado(
            regla=regla, pagina=1, tamano=20, buscar=None,
            segmento='verificadas_publicas', ventana_horas=24, umbral=5,
            min_resenas=3, min_comun=3, _=None, db=object(), neo4j=None,
        )

    def test_f04_stays_available_without_neo4j(self):
        expected = {'items': [{'id': 17}], 'total': 1}
        with patch.object(fraud, 'listar_sin_compra_mysql', return_value=expected), \
             patch.object(fraud, 'enriquecer_nombres_producto') as enrich:
            self.assertEqual(self.call_rule('sin_compra'), expected)
            enrich.assert_not_called()

    def test_graph_rules_are_pending_not_reported_as_zero(self):
        with self.assertRaises(HTTPException) as error:
            self.call_rule('bombardeo')
        self.assertEqual(error.exception.status_code, 503)


if __name__ == '__main__':
    unittest.main()
