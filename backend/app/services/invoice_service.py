"""Genera facturas PDF para pedidos confirmados usando ReportLab."""
from datetime import datetime, timezone, timedelta
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

GT_TZ = timezone(timedelta(hours=-6))

BRAND   = colors.HexColor('#3B82F6')
MUTED   = colors.HexColor('#6B7280')
DARK    = colors.HexColor('#111827')
LIGHT   = colors.HexColor('#F9FAFB')
BORDER  = colors.HexColor('#E5E7EB')


def _fmt_q(amount) -> str:
    return f'Q{float(amount):,.2f}'


def _now_gt() -> str:
    return datetime.now(tz=GT_TZ).strftime('%d/%m/%Y %H:%M')


def generar_factura_pdf(pedido, usuario, direccion) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )
    base = getSampleStyleSheet()
    right = ParagraphStyle('right', parent=base['Normal'], alignment=TA_RIGHT)
    center = ParagraphStyle('center', parent=base['Normal'], alignment=TA_CENTER)
    small_muted = ParagraphStyle('sm', parent=base['Normal'], fontSize=8, textColor=MUTED)
    sm_center = ParagraphStyle('smc', parent=base['Normal'], fontSize=8,
                               textColor=MUTED, alignment=TA_CENTER)
    story = []

    # ── Encabezado ────────────────────────────────────────────────────────────
    story.append(Table(
        [[
            Paragraph('<font size="24" color="#3B82F6"><b>TiendaYa</b></font>', base['Normal']),
            Paragraph(
                '<font size="20"><b>FACTURA</b></font><br/>'
                f'<font size="10" color="#6B7280">N.° {pedido.id:06d}</font>',
                right,
            ),
        ]],
        colWidths=[9*cm, 9*cm],
        style=[('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
               ('BOTTOMPADDING', (0, 0), (-1, -1), 10)],
    ))
    story.append(HRFlowable(width='100%', thickness=1, color=BORDER, spaceAfter=10))

    # ── Metadatos del pedido ──────────────────────────────────────────────────
    referencia = pedido.pagos[0].referencia_transaccion if pedido.pagos else '—'
    story.append(Table(
        [
            ['Fecha:', _now_gt(),     'Referencia pago:', referencia],
            ['Estado:', pedido.estado.capitalize(), '', ''],
        ],
        colWidths=[3*cm, 6*cm, 3.5*cm, 5.5*cm],
        style=[
            ('FONTNAME',  (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME',  (2, 0), (2, -1), 'Helvetica-Bold'),
            ('FONTSIZE',  (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (0, -1), MUTED),
            ('TEXTCOLOR', (2, 0), (2, -1), MUTED),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ],
    ))
    story.append(Spacer(1, 14))

    # ── Cliente y dirección ───────────────────────────────────────────────────
    dir_parts = [direccion.linea1]
    if direccion.linea2:
        dir_parts.append(direccion.linea2)
    dir_parts.append(f'{direccion.municipio}, {direccion.departamento}')
    dir_parts.append(direccion.pais)

    tel = f'<br/><font color="#6B7280">{usuario.telefono}</font>' if usuario.telefono else ''
    story.append(Table(
        [
            [Paragraph('<b>Facturado a</b>', base['Normal']),
             Paragraph('<b>Dirección de envío</b>', base['Normal'])],
            [
                Paragraph(
                    f'{usuario.nombre} {usuario.apellido}<br/>'
                    f'<font color="#6B7280">{usuario.email}</font>{tel}',
                    base['Normal'],
                ),
                Paragraph('<br/>'.join(dir_parts), base['Normal']),
            ],
        ],
        colWidths=[9*cm, 9*cm],
        style=[
            ('FONTSIZE',     (0, 0), (-1, -1), 9),
            ('BACKGROUND',   (0, 0), (-1,  0), LIGHT),
            ('FONTNAME',     (0, 0), (-1,  0), 'Helvetica-Bold'),
            ('TOPPADDING',   (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 6),
            ('LEFTPADDING',  (0, 0), (-1, -1), 8),
            ('BOX',          (0, 0), (-1, -1), 0.5, BORDER),
            ('INNERGRID',    (0, 0), (-1, -1), 0.5, BORDER),
        ],
    ))
    story.append(Spacer(1, 18))

    # ── Tabla de productos ────────────────────────────────────────────────────
    rows = [['Producto', 'Cant.', 'Precio unit.', 'Subtotal']]
    for linea in pedido.lineas:
        rows.append([
            linea.producto_nombre,
            str(linea.cantidad),
            _fmt_q(linea.precio_unitario),
            _fmt_q(linea.subtotal_linea),
        ])

    prod_table = Table(rows, colWidths=[9.5*cm, 2*cm, 3.25*cm, 3.25*cm])
    prod_table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1,  0), BRAND),
        ('TEXTCOLOR',     (0, 0), (-1,  0), colors.white),
        ('FONTNAME',      (0, 0), (-1,  0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, -1), 9),
        ('ALIGN',         (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN',         (0, 0), ( 0, -1), 'LEFT'),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, LIGHT]),
        ('BOX',           (0, 0), (-1, -1), 0.5, BORDER),
        ('INNERGRID',     (0, 0), (-1, -1), 0.5, BORDER),
    ]))
    story.append(prod_table)
    story.append(Spacer(1, 12))

    # ── Totales ───────────────────────────────────────────────────────────────
    story.append(Table(
        [
            ['Subtotal (sin IVA):', _fmt_q(pedido.subtotal)],
            ['IVA incluido (12%):', _fmt_q(pedido.impuestos)],
            ['TOTAL:', _fmt_q(pedido.total)],
        ],
        colWidths=[14*cm, 4*cm],
        style=[
            ('FONTSIZE',     (0,  0), (-1, -2), 9),
            ('FONTSIZE',     (0, -1), (-1, -1), 11),
            ('FONTNAME',     (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR',    (0, -1), (-1, -1), BRAND),
            ('ALIGN',        (0,  0), (-1, -1), 'RIGHT'),
            ('TOPPADDING',   (0,  0), (-1, -1), 4),
            ('BOTTOMPADDING',(0,  0), (-1, -1), 4),
            ('LINEABOVE',    (0, -1), (-1, -1), 1.5, BRAND),
        ],
    ))

    story.append(Spacer(1, 28))
    story.append(HRFlowable(width='100%', thickness=0.5, color=BORDER, spaceAfter=8))
    story.append(Paragraph(
        'Gracias por tu compra en TiendaYa. '
        'Este documento es el comprobante oficial de tu pedido.',
        sm_center,
    ))

    doc.build(story)
    return buffer.getvalue()
