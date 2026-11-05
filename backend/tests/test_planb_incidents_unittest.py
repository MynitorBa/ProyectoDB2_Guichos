"""Pruebas locales puras: ejecutar directamente para evitar fixtures de integración."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import salud
from app.services import planb_incident_service as incidents


class IncidentTests(unittest.TestCase):
    def test_transition_is_deduplicated_and_recoverable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'incidents.sqlite3'
            incidents.record_outage('mysql', 'OperationalError', path=path)
            incidents.record_outage('mysql', 'OperationalError', path=path)
            active = incidents.list_incidents(path=path)
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0]['estado'], 'activo')
            self.assertEqual(active[0]['codigo_error'], 'OperationalError')
            incidents.record_check('mysql', path=path)
            self.assertEqual(len(incidents.list_incidents(path=path)), 1)
            incidents.record_recovery('mysql', path=path)
            recovered = incidents.list_incidents(estado='recuperado', path=path)
            self.assertEqual(len(recovered), 1)
            self.assertGreaterEqual(recovered[0]['duracion_segundos'], 0)
            self.assertEqual(incidents.list_incidents(estado='activo', path=path), [])

    def test_circuit_only_records_significant_transitions(self):
        salud.reiniciar()
        with patch.object(incidents, 'record_outage') as outage, \
             patch.object(incidents, 'record_recovery') as recovery, \
             patch.object(incidents, 'record_check') as check:
            for _ in range(5):
                salud.registrar_falla('redis', 'timeout')
            self.assertEqual(outage.call_count, 1)
            check.assert_not_called()
            salud.registrar_exito('redis')
            salud.registrar_exito('redis')
            self.assertEqual(recovery.call_count, 1)
        salud.reiniciar()

    def test_incident_endpoint_requires_login(self):
        from fastapi.testclient import TestClient
        from app.main import app

        response = TestClient(app).get('/api/v1/admin/sync/incidentes')
        self.assertIn(response.status_code, (401, 403))

    def test_filters_and_restart_preserve_closed_incident_without_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'incidents.sqlite3'
            incidents.record_outage('mysql', 'OperationalError', path=path)
            incidents.record_outage('redis', 'TimeoutError', path=path)
            incidents.record_recovery('mysql', path=path)

            now = datetime.now(timezone.utc)
            mysql = incidents.list_incidents(
                motor='mysql', estado='recuperado',
                desde=now - timedelta(minutes=1), hasta=now + timedelta(minutes=1),
                path=path,
            )
            self.assertEqual(len(mysql), 1)
            self.assertEqual(mysql[0]['codigo_error'], 'OperationalError')
            self.assertNotIn('Traceback', mysql[0]['codigo_error'])
            self.assertEqual(mysql[0]['estado_sync'], 'no_verificado')
            self.assertEqual(
                len(incidents.list_incidents(motor='redis', estado='activo', path=path)), 1,
            )

            # Una conexión nueva simula el siguiente proceso: el archivo es la
            # fuente persistente, no el estado global de Python.
            self.assertEqual(
                incidents.list_incidents(motor='mysql', estado='recuperado', path=path)[0]['id'],
                mysql[0]['id'],
            )


if __name__ == '__main__':
    unittest.main()
