from pathlib import Path

import pytest

from scripts.seed_demo_large import (
    SCALES, complete_paid_line_inventory_ids, load_demo_env, ref_for,
    resolve_offer_rows, should_seed_order, uid_for,
)


SAFE_ENV = """\
TIENDAYA_DEMO=true
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3317
MYSQL_DB=tiendaya_demo
MYSQL_USER=tiendaya_demo
MYSQL_PASSWORD=demo
MONGO_URI=mongodb://demo:demo@127.0.0.1:27117/tiendaya_demo?authSource=admin
MONGO_DB=tiendaya_demo
REDIS_PORT=6389
CASSANDRA_PORT=9142
CASSANDRA_KEYSPACE=tiendaya_analytics_demo
NEO4J_URI=bolt://127.0.0.1:7787
ES_URL=http://127.0.0.1:9210
ES_INDEX_ALIAS=productos_demo
"""


def write_env(tmp_path: Path, value: str) -> Path:
    path = tmp_path / '.env.demo'
    path.write_text(value, encoding='utf-8')
    return path


def test_demo_guard_accepts_isolated_targets(tmp_path):
    config = load_demo_env(write_env(tmp_path, SAFE_ENV))
    assert config['MYSQL_DB'] == 'tiendaya_demo'


@pytest.mark.parametrize(
    ('old', 'new'),
    [
        ('MYSQL_DB=tiendaya_demo', 'MYSQL_DB=tiendaya'),
        ('MYSQL_PORT=3317', 'MYSQL_PORT=3307'),
        ('MONGO_URI=mongodb://demo:demo@127.0.0.1:27117/tiendaya_demo?authSource=admin',
         'MONGO_URI=mongodb://demo:demo@127.0.0.1:27017/tiendaya?authSource=admin'),
        ('NEO4J_URI=bolt://127.0.0.1:7787', 'NEO4J_URI=bolt://127.0.0.1:7687'),
    ],
)
def test_demo_guard_rejects_primary_targets(tmp_path, old, new):
    with pytest.raises(SystemExit, match='Destino inseguro'):
        load_demo_env(write_env(tmp_path, SAFE_ENV.replace(old, new)))


def test_identifiers_are_reproducible_and_profiles_are_ordered():
    assert ref_for('run-a', 'product', 1) == ref_for('run-a', 'product', 1)
    assert uid_for('run-a', 'order', 1) == uid_for('run-a', 'order', 1)
    assert ref_for('run-a', 'product', 1) != ref_for('run-a', 'product', 2)
    assert SCALES['small'].orders < SCALES['medium'].orders < SCALES['full'].orders


def test_offer_resolution_uses_variant_and_seller_when_sku_is_shared():
    meta = [
        ('a' * 24, 'var-a', 7, 'SHARED-SKU', 1135, 30),
        ('b' * 24, 'var-b', 8, 'SHARED-SKU', 1183, 31),
    ]
    resolved = resolve_offer_rows(
        meta, {'var-a': 96, 'var-b': 97}, {(96, 7): 149, (97, 8): 150},
    )
    assert [row[0] for row in resolved] == [149, 150]


def test_incremental_seed_preserves_existing_order_lines():
    assert should_seed_order(0)
    assert not should_seed_order(1)
    assert not should_seed_order(2)


def test_incremental_seed_loads_inventory_for_paid_offer_from_small():
    looked_up = []

    def lookup(offer_ids):
        looked_up.extend(offer_ids)
        return {136: 74}

    result = complete_paid_line_inventory_ids(
        {149: 83}, [{'oferta_id': 136}, {'oferta_id': 149}], lookup,
    )
    assert looked_up == [136]
    assert result == {136: 74, 149: 83}


def test_incremental_seed_rejects_paid_offer_without_inventory():
    with pytest.raises(RuntimeError, match='136'):
        complete_paid_line_inventory_ids(
            {149: 83}, [{'oferta_id': 136}], lambda offer_ids: {},
        )
