"""Genera gráficos SVG de las mediciones Plan B sin dependencias externas."""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'benchmarks/results/20261101'
OUT = ROOT / 'docs/evidencia/planb'
OUT.mkdir(parents=True, exist_ok=True)


def text(x, y, value, size=14, fill='#1f2937', weight='normal'):
    return (f'<text x="{x}" y="{y}" font-family="Arial,sans-serif" font-size="{size}" '
            f'fill="{fill}" font-weight="{weight}">{value}</text>')


def rect(x, y, w, h, fill):
    return f'<rect x="{x}" y="{y}" width="{w:.1f}" height="{h}" rx="4" fill="{fill}"/>'


def svg(parts, height):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="1040" height="%d" '
            'viewBox="0 0 1040 %d"><rect width="1040" height="%d" fill="#fff"/>'
            '%s</svg>' % (height, height, height, ''.join(parts)))


queries = [
    ('admin_trends', 'Administrador · tendencias', [DATA / f'run{i}/analitica.json' for i in range(1, 6)]),
    ('vendor_trends', 'Vendedor · tendencias', [DATA / f'vendor_trends-run{i}/analitica.json' for i in range(1, 4)]),
    ('product_trend', 'Producto · seguimiento', [DATA / f'product_trend-run{i}/analitica.json' for i in range(1, 4)]),
    ('vendor_product_trend', 'Vendedor/producto · seguimiento',
     [DATA / f'vendor_product_trend-run{i}/analitica.json' for i in range(1, 4)]),
]
parts = [text(32, 35, 'Latencia media por consulta analítica (ms)', 21, weight='bold'),
         text(32, 60, 'Mismos datos y funciones; Cassandra y respaldo MySQL aislados', 13, '#64748b'),
         rect(700, 25, 16, 16, '#4f46e5'), text(724, 38, 'Cassandra', 13),
         rect(835, 25, 16, 16, '#0d9488'), text(859, 38, 'MySQL', 13)]
for n, (_, label, files) in enumerate(queries):
    runs = [json.loads(file.read_text(encoding='utf-8')) for file in files]
    c = statistics.mean(run['latencia']['cassandra']['promedio_ms'] for run in runs)
    m = statistics.mean(run['latencia']['mysql_respaldo']['promedio_ms'] for run in runs)
    y = 105 + n * 100
    parts += [text(32, y + 6, label, 14, weight='bold'),
              rect(320, y - 14, c * 7.5, 24, '#4f46e5'), text(325 + c * 7.5, y + 4, f'{c:.1f}', 13),
              rect(320, y + 16, m * 7.5, 24, '#0d9488'), text(325 + m * 7.5, y + 34, f'{m:.1f}', 13)]
parts += [text(32, 510, 'Dataset pequeño: 78 líneas elegibles. Esta figura no compara escalabilidad general.',
               12, '#64748b')]
(OUT / 'latencia-analitica.svg').write_text(svg(parts, 535), encoding='utf-8')

rows = json.loads((DATA / 'carga_ab_c.json').read_text(encoding='utf-8'))
parts = [text(32, 35, 'Impacto en una reserva de inventario simulada', 21, weight='bold'),
         text(32, 60, 'Transacción aislada con UPDATE y ROLLBACK; no es un checkout completo', 13, '#64748b'),
         rect(725, 24, 16, 16, '#f59e0b'), text(749, 37, 'Promedio', 13),
         rect(855, 24, 16, 16, '#dc2626'), text(879, 37, 'p95', 13)]
for n, (case, label) in enumerate([('A', 'A · Cassandra sirve estadísticas'),
                                    ('B', 'B · MySQL sirve estadísticas'),
                                    ('C', 'C · MySQL recibe más consultas')]):
    selected = [row['inventario_proxy'] for row in rows if row['escenario'] == case]
    avg = statistics.mean(row['promedio_ms'] for row in selected)
    p95 = statistics.mean(row['p95_ms'] for row in selected)
    y = 115 + n * 108
    parts += [text(32, y + 8, label, 14, weight='bold'),
              rect(330, y - 15, avg * 18, 25, '#f59e0b'), text(335 + avg * 18, y + 4, f'{avg:.1f} ms', 13),
              rect(330, y + 18, p95 * 18, 25, '#dc2626'), text(335 + p95 * 18, y + 37, f'{p95:.1f} ms', 13)]
parts += [text(32, 477, 'Dos repeticiones de 15 s por escenario; el equipo Windows también tenía otras cargas.',
               12, '#64748b')]
(OUT / 'impacto-inventario.svg').write_text(svg(parts, 500), encoding='utf-8')
print(OUT / 'latencia-analitica.svg')
print(OUT / 'impacto-inventario.svg')
