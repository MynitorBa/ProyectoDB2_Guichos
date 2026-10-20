"""Enriquecimiento de lectura para el panel; no conecta a las bases DEMO."""
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace as Row

from app.models.pago import Pago
from app.models.pedido import Pedido, PedidoLinea
from app.models.producto_referencia import ProductoReferencia
from app.models.resena import Resena
from app.models.usuario import Usuario
from app.models.vendedor import Vendedor
from app.services.fraud_detection_service import (
    enriquecer_expedientes, enriquecer_resenas_indicador,
    listar_sin_compra_mysql,
)


class Query:
    def __init__(self, rows):
        self.rows = rows
        self.start = 0
        self.size = None

    def join(self, *_args):
        return self

    def filter(self, *_args):
        return self

    def outerjoin(self, *_args):
        return self

    def with_entities(self, *_args):
        return self

    def scalar(self):
        return len(self.rows)

    def offset(self, start):
        self.start = start
        return self

    def limit(self, size):
        self.size = size
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return self.rows[self.start:self.start + self.size] if self.size is not None else self.rows


class Db:
    def __init__(self, rows):
        self.rows = rows

    def query(self, *models):
        return Query(self.rows.get(models, []))


def test_f01_f02_f03_reviews_are_enriched_in_one_batch_each():
    when = datetime(2026, 10, 1, 12)
    review = Row(public_id='rv-1', comentario='Comentario completo',
                 calificacion=4, fecha=when, verificada_compra=True,
                 estado_moderacion='aprobada')
    user = Row(nombre='Ana', apellido='García')
    db = Db({(Resena, Usuario): [(review, user)]})
    for rule, items in [
        ('bombardeo', [{'resenas': [{'resena_id': 'rv-1'}]}]),
        ('reviewer_unico_vendedor', [{'resenas': [{'resena_id': 'rv-1'}]}]),
        ('cluster', [{'productos': [{'resenas': [
            {'resena1_id': 'rv-1', 'resena2_id': 'rv-missing'},
        ]}]}]),
    ]:
        enriquecer_resenas_indicador(db, rule, items)
        detail = (items[0]['productos'][0]['resenas'][0]['resena1_detalle']
                  if rule == 'cluster' else items[0]['resenas'][0])
        assert detail['comentario'] == 'Comentario completo'
        assert detail['calificacion'] == 4
        assert detail['usuario_nombre'] == 'Ana García'
    assert items[0]['productos'][0]['resenas'][0]['resena2_detalle'] == {}


def test_commercial_details_keep_original_evidence_and_only_attributable_purchase():
    when = datetime(2026, 10, 1, 12)
    line = Row(id=7, pedido_id=3, oferta_id=8, producto_nombre='Mouse',
               cantidad=2, subtotal_linea=Decimal('80.00'))
    order = Row(id=3, estado='confirmado')
    payment = Row(pedido_id=3, estado='aprobado', fecha=when)
    review = Row(public_id='rv-1', calificacion=5, comentario=None,
                 fecha=when, verificada_compra=True)
    user = Row(id=4, nombre='Ana', apellido='García')
    db = Db({
        (PedidoLinea,): [line], (Pedido,): [order], (Pago,): [payment],
        (Resena, Usuario): [(review, user)], (Usuario,): [user],
    })
    original = {'lineas': [7], 'resenas_ligadas': ['rv-1']}
    items = [
        {'tipo': 'autocompra', 'oferta_id': 8, 'evidencias': original},
        {'tipo': 'inventario_atipico', 'evidencias': {'movimientos_detalle': [
            {'movimiento_id': 9, 'responsable_usuario_id': 4},
        ]}},
        {'tipo': 'coincidencia_cantidad', 'evidencias': {'pares_confirmados': [
            {'linea_id': 7, 'movimiento_id': 9},
        ]}},
    ]
    enriquecer_expedientes(db, items)
    purchase = items[0]['detalle_investigacion']['compras'][0]
    assert purchase['pedido_id'] == 3
    assert purchase['estado_pago'] == 'aprobado'
    assert purchase['importe'] == '80.00'
    assert items[0]['detalle_investigacion']['resenas'][0]['comentario'] is None
    assert items[0]['evidencias'] is original
    assert items[1]['detalle_investigacion']['movimientos'][0]['responsable_nombre'] == 'Ana García'
    assert items[2]['evidencias']['pares_confirmados'][0]['linea_id'] == 7


def test_f04_returns_full_comment_with_server_pagination():
    when = datetime(2026, 10, 1, 12)
    rows = [(
        Row(public_id=f'rv-{i}', calificacion=4, comentario=f'Texto {i}',
            fecha=when, estado_moderacion='pendiente', verificada_compra=False,
            motivo_no_verificada='Sin línea', pedido_linea_id=None, vendedor_id=3),
        Row(id=i, nombre='Ana', apellido='García'),
        Row(producto_ref=f'producto-{i}'),
        Row(id=3, nombre_comercial='Tienda DEMO'),
    ) for i in range(2)]
    db = Db({(Resena, Usuario, ProductoReferencia, Vendedor): rows})
    page = listar_sin_compra_mysql(db, pagina=2, tamano=1)
    assert page['total'] == 2
    assert page['paginas'] == 2
    assert page['items'][0]['comentario'] == 'Texto 1'
    assert page['items'][0]['usuario_nombre'] == 'Ana García'
