"""Ejecutor pequeño para scripts MySQL versionados que usan DELIMITER."""

from pathlib import Path

import pymysql


def iter_statements(script: str):
    delimiter = ';'
    buffer: list[str] = []

    for line in script.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith('DELIMITER '):
            if buffer and ''.join(buffer).strip():
                raise ValueError('Cambio de DELIMITER con una sentencia incompleta')
            delimiter = stripped.split(maxsplit=1)[1]
            continue

        buffer.append(line + '\n')
        joined = ''.join(buffer).rstrip()
        if joined.endswith(delimiter):
            statement = joined[:-len(delimiter)].strip()
            buffer = []
            if statement:
                yield statement

    if ''.join(buffer).strip():
        raise ValueError('El archivo SQL termina con una sentencia incompleta')


def run_sql_file(connection: pymysql.Connection, path: Path) -> int:
    count = 0
    script = path.read_text(encoding='utf-8-sig')
    with connection.cursor() as cursor:
        for statement in iter_statements(script):
            cursor.execute(statement)
            count += 1
    return count
