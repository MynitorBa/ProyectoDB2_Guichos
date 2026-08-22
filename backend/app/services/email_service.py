"""Envío de correos electrónicos vía SMTP (smtplib estándar, sin dependencias extras)."""
import logging
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


def enviar_factura_por_correo(
    email_destino: str,
    nombre: str,
    pedido_id: int,
    total: float,
    pdf_bytes: bytes,
) -> None:
    """
    Envía la factura PDF como adjunto al correo del usuario.
    Si SMTP_USER o SMTP_PASSWORD están vacíos, la función simplemente loguea
    una advertencia y retorna sin error para no interrumpir el checkout.
    """
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning(
            'SMTP no configurado (SMTP_USER/SMTP_PASSWORD vacíos) — '
            'no se enviará el correo de la factura del pedido #%d.', pedido_id
        )
        return

    msg = MIMEMultipart()
    msg['From'] = f'{settings.SMTP_FROM_NAME} <{settings.SMTP_USER}>'
    msg['To'] = email_destino
    msg['Subject'] = f'Tu factura — Pedido N.° {pedido_id:06d} | TiendaYa'

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #111827; max-width: 560px; margin: 0 auto;">
      <div style="background:#3B82F6; padding:24px 32px; border-radius:8px 8px 0 0;">
        <h1 style="color:white; margin:0; font-size:24px;">TiendaYa</h1>
      </div>
      <div style="border:1px solid #E5E7EB; border-top:none; padding:28px 32px; border-radius:0 0 8px 8px;">
        <h2 style="color:#111827; font-size:20px; margin-top:0;">
          ¡Gracias por tu compra, {nombre}!
        </h2>
        <p style="color:#4B5563; font-size:15px;">
          Tu pedido <strong>N.° {pedido_id:06d}</strong> ha sido confirmado.
          El total de tu compra fue <strong style="color:#3B82F6;">Q{total:,.2f}</strong>.
        </p>
        <p style="color:#4B5563; font-size:15px;">
          Adjunto a este correo encontrarás tu <strong>factura en PDF</strong>.
          Guárdala como comprobante de tu compra.
        </p>
        <hr style="border:none; border-top:1px solid #E5E7EB; margin:24px 0;" />
        <p style="color:#9CA3AF; font-size:12px; margin:0;">
          TiendaYa — Guatemala. Este es un correo automático, por favor no respondas a este mensaje.
        </p>
      </div>
    </body>
    </html>
    """
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    pdf_part = MIMEApplication(pdf_bytes, _subtype='pdf')
    pdf_part.add_header(
        'Content-Disposition', 'attachment',
        filename=f'factura-TiendaYa-{pedido_id:06d}.pdf',
    )
    msg.attach(pdf_part)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.sendmail(settings.SMTP_USER, email_destino, msg.as_string())
        logger.info('Factura pedido #%d enviada a %s', pedido_id, email_destino)
    except Exception as exc:
        logger.error('Error al enviar factura pedido #%d a %s: %s', pedido_id, email_destino, exc)
