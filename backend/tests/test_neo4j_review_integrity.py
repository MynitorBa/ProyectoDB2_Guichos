from pathlib import Path
import pytest
from sqlalchemy import text

from app.core.db_mysql import SessionLocal
from app.services import review_mysql_service
from app.services.review_service import registrar_compra
from app.services.recommendation_service import referencias_relacionadas
from app.services.fraud_detection_service import (
    detectar_autocompras, detectar_flash_pagadas, resumen_flash_pagadas,
)


class _Result:
    def __init__(self, row=None):
        self._row = row

    def single(self):
        return self._row

    def data(self):
        return self._row or []


class _Session:
    def __init__(self, row=None):
        self.row = row
        self.query = None
        self.params = None

    def run(self, query, **params):
        self.query = query
        self.params = params
        return _Result(self.row)


def test_purchase_projection_is_identified_by_line_and_records_seller():
    session = _Session()

    registrar_compra(
        session, 7, 'a' * 24, 10, 20, '2026-10-17T10:00:00+00:00',
        linea_id=30, vendedor_id=40,
    )

    assert 'MERGE (c:Compra {linea_id: $linea_id})' in session.query
    assert 'MERGE (u)-[:REALIZO]->(c)' in session.query
    assert 'MERGE (c)-[:A_VENDEDOR]->(v)' in session.query
    assert ':COMPRO' not in session.query
    assert session.params['linea_id'] == 30
    assert session.params['vendedor_id'] == 40


def test_review_seller_must_match_a_paid_mysql_purchase():
    service = (
        Path(__file__).resolve().parents[1]
        / 'app' / 'services' / 'review_mysql_service.py'
    ).read_text(encoding='utf-8')

    assert 'PedidoVendedor.vendedor_id == vendedor_id' in service
    assert "Pago.estado == 'aprobado'" in service
    assert 'Pedido.estado.notin_(ESTADOS_PEDIDO_INVALIDOS)' in service


def test_mysql_enforces_one_review_per_user_product_and_seller():
    migration = (
        Path(__file__).resolve().parents[2]
        / 'database' / 'mysql' / '21_review_authority.sql'
    ).read_text(encoding='utf-8')

    assert 'uq_resenas_usuario_producto_vendedor' in migration
    assert '(usuario_id, producto_referencia_id, vendedor_id)' in migration


def test_review_reconciliation_never_uses_a_future_purchase():
    script = (
        Path(__file__).resolve().parents[1]
        / 'scripts' / 'apply_review_authority.py'
    ).read_text(encoding='utf-8')

    assert 'p.fecha_creacion <= %s' in script
    assert "'sin_compra_pagada_atribuible'" in script


def test_recommendations_count_distinct_buyers_and_can_exclude_owned_products():
    session = _Session([{'producto_ref': 'b' * 24, 'compradores_comunes': 2}])

    rows = referencias_relacionadas(session, 'a' * 24, usuario_id=7, limite=4)

    assert rows[0]['compradores_comunes'] == 2
    assert 'count(DISTINCT u)' in session.query
    assert 'NOT EXISTS' in session.query
    assert session.params['uid'] == 7


def test_fraud_queries_use_paid_purchase_nodes_and_not_reservations():
    self_session = _Session([])
    detectar_autocompras(self_session)
    assert ':GESTIONA' in self_session.query
    assert ':Compra' in self_session.query

    flash_session = _Session([])
    detectar_flash_pagadas(flash_session)
    assert 'c.promocion_flash_id IS NOT NULL' in flash_session.query
    assert 'c.pagada = true' in flash_session.query

    summary_session = _Session([])
    resumen_flash_pagadas(summary_session)
    assert 'count(DISTINCT usuario_id)' in summary_session.query
    assert 'concentracion_max_comprador_pct' in summary_session.query


def test_review_projection_uses_final_seller_relationship():
    service = (
        Path(__file__).resolve().parents[1]
        / 'app' / 'services' / 'review_service.py'
    ).read_text(encoding='utf-8')
    assert 'MERGE (r)-[:CALIFICA_A]->(v)' in service


def test_offer_changes_are_routed_to_neo4j():
    from app.services.outbox_service import destinos_de

    assert 'neo4j' in destinos_de('oferta.estado_actualizado')
    assert 'neo4j' in destinos_de('oferta.vendedor_actualizado')
    assert 'neo4j' in destinos_de('producto.oferta_principal_actualizada')


def test_functional_consumers_no_longer_read_or_write_legacy_compro():
    backend = Path(__file__).resolve().parents[1]
    paths = [
        backend / 'app' / 'services' / 'review_service.py',
        backend / 'app' / 'services' / 'outbox_service.py',
        backend / 'scripts' / 'demo_fallas.py',
        backend / 'scripts' / 'simulate_fraud.py',
        backend / 'scripts' / 'seed_reviews.py',
    ]

    for path in paths:
        assert ':COMPRO' not in path.read_text(encoding='utf-8'), path


def test_failure_demo_validates_complete_purchase_node():
    script = (
        Path(__file__).resolve().parents[1]
        / 'scripts' / 'demo_fallas.py'
    ).read_text(encoding='utf-8')

    assert ':REALIZO' in script
    assert ':DE_PRODUCTO' in script
    assert ':A_VENDEDOR' in script


def test_review_create_duplicate_and_edit_are_enforced_transactionally():
    db = SessionLocal()
    try:
        candidate = db.execute(text("""
            SELECT p.usuario_id, pl.producto_ref, pv.vendedor_id
            FROM pedido_lineas pl
            JOIN pedidos p ON p.id=pl.pedido_id
            JOIN pedido_vendedores pv ON pv.id=pl.pedido_vendedor_id
            JOIN producto_referencias pr ON pr.producto_ref=pl.producto_ref
            LEFT JOIN resenas r
              ON r.usuario_id=p.usuario_id
             AND r.producto_referencia_id=pr.id
             AND r.vendedor_id=pv.vendedor_id
            WHERE p.estado NOT IN ('cancelado','reembolsado')
              AND EXISTS (SELECT 1 FROM pagos pa
                          WHERE pa.pedido_id=p.id AND pa.estado='aprobado')
              AND r.id IS NULL
            LIMIT 1
        """)).mappings().first()
        if not candidate:
            pytest.skip('No queda una combinación elegible sin reseña en esta instancia.')
        review = review_mysql_service.crear(
            db, usuario_id=candidate['usuario_id'],
            producto_ref=candidate['producto_ref'],
            vendedor_id=candidate['vendedor_id'], calificacion=5,
            texto='Prueba transaccional temporal',
        )
        with pytest.raises(FileExistsError):
            review_mysql_service.crear(
                db, usuario_id=candidate['usuario_id'],
                producto_ref=candidate['producto_ref'],
                vendedor_id=candidate['vendedor_id'], calificacion=4,
                texto='No debe duplicarse',
            )
        edited = review_mysql_service.editar(
            db, public_id=review.public_id,
            usuario_id=candidate['usuario_id'], calificacion=4,
            texto='Edición transaccional temporal',
        )
        assert edited.version == 2
    finally:
        db.rollback()
        db.close()
