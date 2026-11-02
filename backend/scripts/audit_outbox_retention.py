"""Auditoría de solo lectura para diseñar la retención del Outbox.

No contiene ninguna sentencia DELETE. Los candidatos son orientativos:
todavía falta clasificar dependencias de auditoría y reconstrucción.
"""

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.db_mysql import engine  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retencion-dias', type=int, default=90)
    args = parser.parse_args()
    if args.retencion_dias < 1:
        parser.error('La retención debe ser positiva')
    with engine.connect() as db:
        status = [dict(row) for row in db.execute(text('''
            SELECT destino, estado, COUNT(*) AS eventos,
                   MIN(creado_en) AS mas_antiguo, MAX(creado_en) AS mas_reciente
            FROM outbox_eventos GROUP BY destino, estado
        ''')).mappings()]
        by_day = [dict(row) for row in db.execute(text('''
            SELECT DATE(procesado_en) AS dia, COUNT(*) AS eventos
            FROM outbox_eventos WHERE estado='procesado' AND procesado_en IS NOT NULL
            GROUP BY DATE(procesado_en) ORDER BY dia DESC LIMIT 30
        ''')).mappings()]
        eligible = [dict(row) for row in db.execute(text('''
            SELECT destino, tipo_evento, COUNT(*) AS candidatos
            FROM outbox_eventos
            WHERE estado='procesado'
              AND procesado_en < UTC_TIMESTAMP(6) - INTERVAL :days DAY
            GROUP BY destino, tipo_evento
        '''), {'days': args.retencion_dias}).mappings()]
        size = dict(db.execute(text('''
            SELECT table_rows, data_length, index_length, data_free
            FROM information_schema.tables
            WHERE table_schema=DATABASE() AND table_name='outbox_eventos'
        ''')).mappings().one())
    print(json.dumps({
        'modo': 'dry-run', 'retencion_dias': args.retencion_dias,
        'por_estado': status, 'procesados_por_dia': by_day,
        'candidatos_no_aprobados': eligible, 'tamano_innodb': size,
    }, default=str, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
