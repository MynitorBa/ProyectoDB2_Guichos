"""Conciliaciones históricas explícitas, auditables e idempotentes.

Este módulo no llama a la pasarela. La evidencia del ledger se lee en modo
SQLite ``ro`` y la única escritura ocurre en una transacción MySQL provista
por el llamador.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import closing
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.checkout_saga import CheckoutSagaPaso
from app.models.conciliacion_historica import ConciliacionHistorica
from app.models.inventario import Inventario, MovimientoInventario
from app.models.oferta import Oferta
from app.models.outbox import OutboxEvento
from app.models.pago import Pago
from app.models.pedido import Pedido, PedidoLinea
from app.models.pedido_envio import PedidoEnvio, PedidoEnvioLinea
from app.models.pedido_vendedor import PedidoVendedor
from app.models.promocion_flash import ReservaFlash
from app.models.usuario import Usuario
from app.services.offer_history_service import registrar_saldo_inventario
from app.services.outbox_service import enqueue_outbox


TIPO = 'pago_aprobado_entrega_historica_v1'
ENTORNO = 'demo'
PEDIDO_ID = 1851
PAGO_ID = 1847
LINEA_ID = 2546
OFERTA_ID = 768
INVENTARIO_ID = 507
RESERVA_ID = 2753
ENVIO_ID = 29
COBRO_ID = 'ch_aa444fb6f6ee4289'
CLAVE_IDEMPOTENCIA = '90e50e34-e606-41fc-bb1d-9c87e91e10ad'
MONTO = Decimal('10000.00')
MONEDA = 'GTQ'
REFERENCIA = 'PED-00001851'


class ConciliacionError(RuntimeError):
    """Una precondición cambió o la evidencia dejó de ser inequívoca."""


class FallaConciliacionSimulada(RuntimeError):
    """Falla deliberada usada para demostrar rollback antes del commit."""


def leer_cobro_ledger(ledger: Path, clave_idempotencia: str) -> dict:
    """Lee una sola transacción sin permitir que SQLite cree o modifique el archivo."""
    path = ledger.resolve()
    if not path.is_file() or path.name != 'ledger.demo.db':
        raise ConciliacionError('Se requiere el ledger.demo.db existente.')
    uri = f'file:{path.as_posix()}?mode=ro'
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            'SELECT clave,id,monto,moneda,referencia,estado,creado_en,actualizado_en '
            'FROM cobros WHERE clave=?',
            (clave_idempotencia,),
        ).fetchone()
    if row is None:
        raise ConciliacionError('El ledger DEMO no contiene el cobro esperado.')
    return dict(row)


def huella_conciliacion(clave_idempotencia: str) -> str:
    material = {
        'version': 1,
        'entorno': ENTORNO,
        'tipo': TIPO,
        'pedido_id': PEDIDO_ID,
        'pago_id': PAGO_ID,
        'linea_id': LINEA_ID,
        'inventario_id': INVENTARIO_ID,
        'reserva_id': RESERVA_ID,
        'cobro_id': COBRO_ID,
        'clave_idempotencia': clave_idempotencia,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def _operacion_id(huella: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'tiendaya:conciliacion:{huella}'))


def _validar_cobro(cobro: dict, clave: str) -> None:
    expected = {
        'clave': clave,
        'id': COBRO_ID,
        'moneda': MONEDA,
        'referencia': REFERENCIA,
        'estado': 'aprobado',
    }
    for field, value in expected.items():
        if cobro.get(field) != value:
            raise ConciliacionError(
                f'El cobro no coincide en {field}: {cobro.get(field)!r} != {value!r}.'
            )
    if Decimal(str(cobro.get('monto'))) != MONTO:
        raise ConciliacionError('El importe del cobro no es Q10,000.00.')


def _eventos_con_huella(db: Session, huella: str) -> list[OutboxEvento]:
    candidates = db.query(OutboxEvento).filter(
        OutboxEvento.agregado_id == str(PEDIDO_ID),
        OutboxEvento.tipo_evento.in_((
            'analytics.pedido_actualizado', 'grafo.compra_registrada',
        )),
    ).all()
    return [event for event in candidates if (event.payload or {}).get('conciliacion_huella') == huella]


def _validar_estado_final(db: Session, registro: ConciliacionHistorica, huella: str) -> dict:
    pedido = db.get(Pedido, PEDIDO_ID)
    pago = db.get(Pago, PAGO_ID)
    inventario = db.get(Inventario, INVENTARIO_ID)
    salidas = db.query(MovimientoInventario).filter_by(
        pedido_id=PEDIDO_ID, inventario_id=INVENTARIO_ID, tipo='salida',
    ).all()
    eventos = _eventos_con_huella(db, huella)
    destinos = sorted((event.tipo_evento, event.destino) for event in eventos)
    esperados = sorted([
        ('analytics.pedido_actualizado', 'analitica_mysql'),
        ('analytics.pedido_actualizado', 'busqueda'),
        ('analytics.pedido_actualizado', 'cassandra'),
        ('grafo.compra_registrada', 'neo4j'),
    ])
    if not pedido or pedido.estado != 'entregado' or pedido.reserva_expira_en is not None:
        raise ConciliacionError('La conciliación registrada no conserva el pedido entregado final.')
    if not pago or pago.estado != 'aprobado' or pago.referencia_pasarela != COBRO_ID:
        raise ConciliacionError('La conciliación registrada no conserva el pago aprobado final.')
    if not inventario or (inventario.cantidad_disponible, inventario.cantidad_reservada) != (8, 0):
        raise ConciliacionError('La conciliación registrada no conserva inventario 8/0.')
    if len(salidas) != 1 or salidas[0].cantidad != 1:
        raise ConciliacionError('La conciliación registrada no tiene exactamente una salida.')
    if destinos != esperados:
        raise ConciliacionError('Las cuatro rutas Outbox de la conciliación no son exactas.')
    return {
        'aplicada': False,
        'ya_aplicada': True,
        'operacion_id': registro.operacion_id,
        'huella': huella,
        'movimiento_salida_id': salidas[0].id,
        'eventos_outbox': len(eventos),
    }


def conciliar_pedido_1851(
    db: Session,
    *,
    cobro: dict,
    responsable_usuario_id: int,
    entorno_db: str,
    fallar_antes_commit: bool = False,
) -> dict:
    """Aplica la corrección dentro de la transacción administrada por el llamador."""
    if entorno_db != 'tiendaya_demo' and not entorno_db.startswith('tiendaya_reconcile_test_'):
        raise ConciliacionError(f'Base no autorizada para la conciliación: {entorno_db}.')

    # El pedido es el primer candado: dos ejecuciones quedan serializadas antes
    # de consultar o insertar la huella única.
    pedido = db.execute(
        select(Pedido).where(Pedido.id == PEDIDO_ID).with_for_update()
    ).scalar_one_or_none()
    if pedido is None:
        raise ConciliacionError('No existe el pedido 1851.')
    huella = huella_conciliacion(pedido.clave_idempotencia)
    existente = db.execute(
        select(ConciliacionHistorica).where(
            ConciliacionHistorica.entorno == ENTORNO,
            ConciliacionHistorica.pedido_id == PEDIDO_ID,
            ConciliacionHistorica.tipo_conciliacion == TIPO,
        ).with_for_update()
    ).scalar_one_or_none()
    if existente:
        if existente.huella != huella or existente.estado != 'aplicada':
            raise ConciliacionError('Existe una conciliación incompatible para el pedido 1851.')
        return _validar_estado_final(db, existente, huella)

    pago = db.execute(
        select(Pago).where(Pago.id == PAGO_ID, Pago.pedido_id == PEDIDO_ID).with_for_update()
    ).scalar_one_or_none()
    linea = db.execute(
        select(PedidoLinea).where(
            PedidoLinea.id == LINEA_ID, PedidoLinea.pedido_id == PEDIDO_ID,
        ).with_for_update()
    ).scalar_one_or_none()
    oferta = db.execute(
        select(Oferta).where(Oferta.id == OFERTA_ID).with_for_update()
    ).scalar_one_or_none()
    inventario = db.execute(
        select(Inventario).where(
            Inventario.id == INVENTARIO_ID, Inventario.oferta_id == OFERTA_ID,
        ).with_for_update()
    ).scalar_one_or_none()
    movimientos = db.execute(
        select(MovimientoInventario).where(
            MovimientoInventario.pedido_id == PEDIDO_ID,
        ).order_by(MovimientoInventario.id).with_for_update()
    ).scalars().all()
    subpedidos = db.execute(
        select(PedidoVendedor).where(PedidoVendedor.pedido_id == PEDIDO_ID).with_for_update()
    ).scalars().all()
    envios = db.execute(
        select(PedidoEnvio).join(
            PedidoVendedor, PedidoVendedor.id == PedidoEnvio.pedido_vendedor_id,
        ).where(PedidoVendedor.pedido_id == PEDIDO_ID).with_for_update()
    ).scalars().all()
    envio_lineas = db.execute(
        select(PedidoEnvioLinea).where(
            PedidoEnvioLinea.envio_id.in_([shipment.id for shipment in envios] or [-1]),
        ).with_for_update()
    ).scalars().all()
    flash = db.execute(
        select(ReservaFlash).where(ReservaFlash.pedido_id == PEDIDO_ID).with_for_update()
    ).scalars().all()
    responsable = db.get(Usuario, responsable_usuario_id)

    if not responsable or 'administrador' not in {role.nombre for role in responsable.roles}:
        raise ConciliacionError('El responsable no es un administrador válido.')
    if pedido.estado != 'entregado' or pedido.clave_idempotencia != CLAVE_IDEMPOTENCIA:
        raise ConciliacionError('El pedido ya no está entregado o cambió su clave idempotente.')
    if not pago or pago.estado != 'en_verificacion' or pago.clave_idempotencia != pedido.clave_idempotencia:
        raise ConciliacionError('El pago ya no es el pago en verificación esperado.')
    if Decimal(pago.monto) != MONTO:
        raise ConciliacionError('El importe MySQL del pago cambió.')
    _validar_cobro(cobro, pedido.clave_idempotencia)
    if not linea or linea.oferta_id != OFERTA_ID or linea.cantidad != 1:
        raise ConciliacionError('La línea 2546 dejó de ser la única unidad de oferta 768 esperada.')
    if db.query(PedidoLinea).filter_by(pedido_id=PEDIDO_ID).count() != 1:
        raise ConciliacionError('El pedido ya no contiene exactamente una línea.')
    if not oferta or oferta.version != 3:
        raise ConciliacionError('La oferta 768 cambió de versión; se detiene la conciliación.')
    if not inventario or (inventario.cantidad_disponible, inventario.cantidad_reservada) != (9, 1):
        raise ConciliacionError('El inventario 507 ya no está en 9/1.')
    if len(movimientos) != 1 or movimientos[0].id != RESERVA_ID or movimientos[0].tipo != 'reserva' or movimientos[0].cantidad != 1:
        raise ConciliacionError('Ya no existe únicamente la reserva 2753 de una unidad.')
    if len(subpedidos) != 1 or subpedidos[0].estado != 'entregado':
        raise ConciliacionError('El subpedido no permanece entregado de forma inequívoca.')
    if len(envios) != 1 or envios[0].id != ENVIO_ID or envios[0].estado != 'entregado':
        raise ConciliacionError('El envío 29 no permanece como la única entrega.')
    if len(envio_lineas) != 1 or envio_lineas[0].pedido_linea_id != LINEA_ID or envio_lineas[0].cantidad != 1:
        raise ConciliacionError('La entrega ya no corresponde exactamente a la línea 2546.')
    if flash:
        raise ConciliacionError('Apareció una reserva flash inesperada para el pedido 1851.')
    if _eventos_con_huella(db, huella):
        raise ConciliacionError('Hay eventos con la huella pero no existe su bitácora atómica.')

    before = {
        'pedido_estado': pedido.estado,
        'pago_estado': pago.estado,
        'inventario': {'disponible': 9, 'reservado': 1},
        'oferta_version': oferta.version,
        'movimiento_reserva_id': RESERVA_ID,
        'envio_id': ENVIO_ID,
        'cobro': {key: cobro.get(key) for key in ('id', 'monto', 'moneda', 'referencia', 'estado')},
    }
    registro = ConciliacionHistorica(
        operacion_id=_operacion_id(huella), entorno=ENTORNO,
        pedido_id=PEDIDO_ID, pago_id=PAGO_ID, tipo_conciliacion=TIPO,
        huella=huella, referencia_cobro=COBRO_ID,
        responsable_usuario_id=responsable_usuario_id, estado='aplicada',
        resultado='pago conciliado y reserva consumida', datos_auditoria={},
    )
    db.add(registro)
    db.flush()  # materializa las restricciones únicas antes de tocar saldos

    inventario.cantidad_disponible = 8
    inventario.cantidad_reservada = 0
    oferta.version += 1
    salida = MovimientoInventario(
        inventario_id=INVENTARIO_ID, tipo='salida', cantidad=1,
        motivo='Conciliación histórica pedido #1851', pedido_id=PEDIDO_ID,
        usuario_id=responsable_usuario_id,
    )
    db.add(salida)
    registrar_saldo_inventario(
        db, inventario=inventario, usuario_id=responsable_usuario_id,
        motivo='Conciliación histórica del pedido #1851',
    )
    pago.estado = 'aprobado'
    pago.referencia_pasarela = COBRO_ID
    pago.referencia_transaccion = COBRO_ID
    pedido.reserva_expira_en = None
    db.add(CheckoutSagaPaso(
        pedido_id=PEDIDO_ID, paso='conciliacion_historica', resultado='ok',
        detalle={'operacion_id': registro.operacion_id, 'huella': huella,
                 'cobro_id': COBRO_ID, 'responsable_usuario_id': responsable_usuario_id},
    ))
    payload = {'motivo': 'conciliacion_historica', 'conciliacion_huella': huella,
               'operacion_id': registro.operacion_id}
    enqueue_outbox(
        db, tipo_evento='analytics.pedido_actualizado', agregado_tipo='pedido',
        agregado_id=PEDIDO_ID, producto_ref=None, payload=payload,
    )
    enqueue_outbox(
        db, tipo_evento='grafo.compra_registrada', agregado_tipo='pedido',
        agregado_id=PEDIDO_ID, producto_ref=None,
        payload={**payload, 'usuario_id': pedido.usuario_id},
    )
    db.flush()
    eventos = _eventos_con_huella(db, huella)
    registro.datos_auditoria = {
        'antes': before,
        'despues': {
            'pedido_estado': pedido.estado,
            'pago_estado': pago.estado,
            'inventario': {'disponible': 8, 'reservado': 0},
            'oferta_version': oferta.version,
            'movimiento_salida_id': salida.id,
            'eventos_outbox': [event.id for event in eventos],
        },
    }
    db.flush()
    if fallar_antes_commit:
        raise FallaConciliacionSimulada('Falla simulada después de escribir y antes del commit.')
    return {
        'aplicada': True,
        'ya_aplicada': False,
        'operacion_id': registro.operacion_id,
        'huella': huella,
        'movimiento_salida_id': salida.id,
        'eventos_outbox': len(eventos),
    }
