import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app.services.historical_reconciliation_service import (
    CLAVE_IDEMPOTENCIA, COBRO_ID, huella_conciliacion, leer_cobro_ledger,
)


class HistoricalReconciliationUnitTests(unittest.TestCase):
    def test_fingerprint_is_stable_and_expected(self):
        self.assertEqual(
            huella_conciliacion(CLAVE_IDEMPOTENCIA),
            '97a974c5d145f5deb70a6692afa7decefc263e447821a9ad87b28fecbf956bbe',
        )
        self.assertNotEqual(
            huella_conciliacion('otra-clave-idempotente'),
            huella_conciliacion(CLAVE_IDEMPOTENCIA),
        )

    def test_ledger_is_read_without_modifying_it(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / 'ledger.demo.db'
            with closing(sqlite3.connect(ledger)) as db:
                db.execute('''CREATE TABLE cobros (
                    clave TEXT PRIMARY KEY, id TEXT, monto TEXT, moneda TEXT,
                    referencia TEXT, estado TEXT, creado_en TEXT, actualizado_en TEXT
                )''')
                db.execute(
                    'INSERT INTO cobros VALUES (?,?,?,?,?,?,?,?)',
                    (CLAVE_IDEMPOTENCIA, COBRO_ID, '10000.00', 'GTQ',
                     'PED-00001851', 'aprobado', 'antes', 'antes'),
                )
                db.commit()
            before = hashlib.sha256(ledger.read_bytes()).hexdigest()
            charge = leer_cobro_ledger(ledger, CLAVE_IDEMPOTENCIA)
            after = hashlib.sha256(ledger.read_bytes()).hexdigest()
            self.assertEqual(charge['id'], COBRO_ID)
            self.assertEqual(charge['estado'], 'aprobado')
            self.assertEqual(before, after)

    def test_migration_has_both_business_uniqueness_guards(self):
        migration = (
            Path(__file__).resolve().parents[2]
            / 'database/mysql/28_historical_reconciliations.sql'
        ).read_text(encoding='utf-8')
        self.assertIn('UNIQUE KEY uq_conciliacion_huella (huella)', migration)
        self.assertIn('uq_conciliacion_entorno_pedido_tipo', migration)


if __name__ == '__main__':
    unittest.main()
