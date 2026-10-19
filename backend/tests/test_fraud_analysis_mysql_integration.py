"""Integración opt-in contra un esquema MySQL desechable, nunca `tiendaya`."""

import os
from contextlib import contextmanager
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models.alerta_fraude import AlertaFraude
from app.models.fraud_analysis_run import FraudAnalysisRun
from app.services import fraud_analysis_service as analysis
from app.services import fraud_detection_service as fraud


TEST_URL = os.getenv('FRAUD_TEST_MYSQL_URL')
pytestmark = pytest.mark.skipif(
    not TEST_URL or TEST_URL.rsplit('/', 1)[-1].split('?', 1)[0] == 'tiendaya',
    reason='Requiere FRAUD_TEST_MYSQL_URL apuntando a un esquema aislado.',
)


class _NeoSession:
    def run(self, *_args, **_kwargs):
        return type('Result', (), {'data': lambda self: []})()


class _Driver:
    @contextmanager
    def session(self):
        yield _NeoSession()


@pytest.fixture()
def isolated_engine():
    engine = create_engine(TEST_URL, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text('DELETE FROM alertas_fraude'))
        connection.execute(text('DELETE FROM fraud_analysis_runs'))
    yield engine
    engine.dispose()


def test_shared_runner_is_idempotent_and_records_manual_and_automatic(
    isolated_engine, monkeypatch,
):
    monkeypatch.setattr(analysis.fraud, 'resumen_fraude', lambda _neo: {
        'bombardeo': {'count': 0}, 'sin_compra_verificada': {'count': 0},
    })
    monkeypatch.setattr(analysis.fraud, 'recalcular_alertas', lambda *_a, **_k: {
        'autocompras': 0, 'inventario_atipico': 0,
    })
    manual = analysis.run_fraud_analysis_once(
        'manual', engine_override=isolated_engine, driver_override=_Driver(),
    )
    automatic = analysis.run_fraud_analysis_once(
        'automatico', engine_override=isolated_engine, driver_override=_Driver(),
    )
    assert manual['estado'] == automatic['estado'] == 'exitosa'
    with Session(isolated_engine) as db:
        assert db.query(FraudAnalysisRun).count() == 2
        assert {row.origen for row in db.query(FraudAnalysisRun).all()} == {
            'manual', 'automatico',
        }


def test_mysql_lock_rejects_second_execution_and_is_released_after_error(
    isolated_engine, monkeypatch,
):
    holder = isolated_engine.connect()
    assert holder.execute(text("SELECT GET_LOCK('tiendaya:fraud-analysis', 0)" )).scalar() == 1
    with pytest.raises(analysis.FraudAnalysisBusy):
        analysis.run_fraud_analysis_once(
            'manual', engine_override=isolated_engine, driver_override=_Driver(),
        )
    holder.execute(text("SELECT RELEASE_LOCK('tiendaya:fraud-analysis')"))
    holder.close()

    monkeypatch.setattr(
        analysis.fraud, 'resumen_fraude',
        lambda _neo: (_ for _ in ()).throw(RuntimeError('neo4j temporalmente caído')),
    )
    with pytest.raises(RuntimeError, match='neo4j'):
        analysis.run_fraud_analysis_once(
            'automatico', engine_override=isolated_engine,
            driver_override=_Driver(),
        )
    with isolated_engine.connect() as connection:
        assert connection.execute(
            text("SELECT GET_LOCK('tiendaya:fraud-analysis', 0)")
        ).scalar() == 1
        connection.execute(text("SELECT RELEASE_LOCK('tiendaya:fraud-analysis')"))
    with Session(isolated_engine) as db:
        failed = db.query(FraudAnalysisRun).order_by(
            FraudAnalysisRun.id.desc()
        ).first()
        assert failed.estado == 'fallida'
        assert 'neo4j temporalmente caído' in failed.error


def test_human_review_survives_redetection_and_missing_signal_becomes_inactive(
    isolated_engine,
):
    with Session(isolated_engine) as db:
        run1 = FraudAnalysisRun(origen='automatico', estado='exitosa')
        run2 = FraudAnalysisRun(origen='manual', estado='exitosa')
        db.add_all([run1, run2])
        db.flush()
        row = fraud._guardar_alerta(
            db, tipo='inventario_atipico', prioridad='baja',
            motivos=['señal inicial'], evidencias={}, oferta_id=None,
        )
        db.flush()
        row.estado = 'descartada'
        row.notas_revision = 'Reposición legítima comprobada'
        db.commit()
        alert_id = row.id

        fraud.recalcular_alertas(
            db, _NeoSession(), ejecucion_id=run1.id, origen='automatico',
            inactivar_ausentes=True,
        )
        row = db.get(AlertaFraude, alert_id)
        assert row.activa is False
        assert row.estado == 'descartada'
        assert row.notas_revision == 'Reposición legítima comprobada'

        fraud._guardar_alerta(
            db, tipo='inventario_atipico', prioridad='media',
            motivos=['detectada otra vez'], evidencias={'version': 2},
            ejecucion_id=run2.id, origen='manual',
        )
        db.commit()
        db.refresh(row)
        assert row.activa is True
        assert row.estado == 'descartada'
        assert row.notas_revision == 'Reposición legítima comprobada'


def test_f06_accepts_only_paid_traceable_sales_without_row_multiplication(
    isolated_engine,
):
    """Pedido/línea/pago/estado/cantidad se validan juntos en MySQL real."""
    connection = isolated_engine.connect()
    transaction = connection.begin()
    try:
        def insert(sql, **params):
            result = connection.execute(text(sql), params)
            return result.lastrowid

        user_id = insert(
            "INSERT INTO usuarios(email,password_hash,nombre,apellido) "
            "VALUES('fraud-fixture@invalid.local','x','Fixture','Fraude')"
        )
        address_id = insert(
            "INSERT INTO direcciones(usuario_id,departamento,municipio,linea1) "
            "VALUES(:user,'Guatemala','Guatemala','Prueba aislada')",
            user=user_id,
        )
        category_id = insert(
            "INSERT INTO categorias(nombre,slug,sku_prefix) "
            "VALUES('Fixture fraude','fixture-fraude','FFZ')"
        )
        product_ref = 'fffffffffffffffffffffff1'
        product_id = insert(
            "INSERT INTO producto_referencias(producto_ref,categoria_id) "
            "VALUES(:ref,:category)", ref=product_ref, category=category_id,
        )
        variant_id = insert(
            "INSERT INTO producto_variante_referencias"
            "(producto_referencia_id,variante_ref) VALUES(:product,:ref)",
            product=product_id, ref='fffffffffffffffffffffff2',
        )
        seller_id = insert(
            "INSERT INTO vendedores(usuario_id,nombre_comercial,nit,estado_verificacion) "
            "VALUES(:user,'Fixture fraude','FRAUD-FIXTURE','verificado')",
            user=user_id,
        )
        offer_id = insert(
            "INSERT INTO ofertas(producto_ref,producto_variante_id,vendedor_id,sku,precio_actual) "
            "VALUES(:ref,:variant,:seller,'FFZ-001',100)",
            ref=product_ref, variant=variant_id, seller=seller_id,
        )
        inventory_id = insert(
            "INSERT INTO inventario(oferta_id,cantidad_disponible) VALUES(:offer,100)",
            offer=offer_id,
        )
        payment_method_id = insert(
            "INSERT INTO metodos_pago(nombre) VALUES('fixture-fraude')"
        )

        def order(state, payment_state, quantities):
            order_id = insert(
                "INSERT INTO pedidos(usuario_id,direccion_id,estado,subtotal,total) "
                "VALUES(:user,:address,:state,100,100)",
                user=user_id, address=address_id, state=state,
            )
            suborder_id = insert(
                "INSERT INTO pedido_vendedores(pedido_id,vendedor_id,estado,subtotal) "
                "VALUES(:order,:seller,:state,100)",
                order=order_id, seller=seller_id, state=state,
            )
            for index, quantity in enumerate(quantities):
                insert(
                    "INSERT INTO pedido_lineas"
                    "(pedido_id,pedido_vendedor_id,oferta_id,producto_ref,sku_snapshot,"
                    "producto_nombre,vendedor_nombre_snapshot,precio_unitario,cantidad,subtotal_linea) "
                    "VALUES(:order,:suborder,:offer,:ref,:sku,'Fixture','Fixture',100,:qty,:subtotal)",
                    order=order_id, suborder=suborder_id, offer=offer_id,
                    ref=product_ref, sku=f'FFZ-{order_id}-{index}', qty=quantity,
                    subtotal=100 * quantity,
                )
            insert(
                "INSERT INTO pagos(pedido_id,metodo_pago_id,monto,estado) "
                "VALUES(:order,:method,100,:state)",
                order=order_id, method=payment_method_id, state=payment_state,
            )
            movement_id = insert(
                "INSERT INTO movimientos_inventario"
                "(inventario_id,tipo,cantidad,motivo,pedido_id,fecha) "
                "VALUES(:inventory,'salida',:qty,'fixture',:order,:date)",
                inventory=inventory_id, qty=sum(quantities), order=order_id,
                date=datetime(2026, 10, 18, 12, 0, 0),
            )
            return movement_id

        valid_single = order('confirmado', 'aprobado', [2])
        valid_multiple_lines = order('entregado', 'aprobado', [1, 2])
        order('pendiente', 'aprobado', [1])
        order('cancelado', 'aprobado', [1])
        order('reembolsado', 'aprobado', [1])
        order('confirmado', 'pendiente', [1])
        insert(
            "INSERT INTO movimientos_inventario"
            "(inventario_id,tipo,cantidad,motivo,pedido_id,fecha) "
            "VALUES(:inventory,'salida',1,'administrativa',NULL,:date)",
            inventory=inventory_id, date=datetime(2026, 10, 18, 12, 0, 0),
        )

        with Session(bind=connection) as db:
            sales = fraud._ventas_pagadas_validas(
                db, oferta_id=offer_id, desde=datetime(2026, 10, 1),
            )
            assert {row.id for row in sales} == {
                valid_single, valid_multiple_lines,
            }
    finally:
        transaction.rollback()
        connection.close()
