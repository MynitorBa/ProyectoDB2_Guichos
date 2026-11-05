from pathlib import Path

import pytest

from scripts.seed_demo_large import (
    SCALES, complete_paid_line_inventory_ids, load_demo_env, ref_for,
    resolve_offer_rows, should_seed_order, uid_for,
    planned_fraud_order, demo_product_name, plan_normal_order, run_tags,
)
from scripts.demo_catalog_data import category_for, demo_person_name, demo_product, demo_store_name


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


def test_medium_fraud_scenarios_are_distinct_and_exclusive():
    users = list(range(1000, 1650))
    sellers = list(range(2000, 2030))
    offers = []
    by_seller = {seller: [] for seller in sellers}
    for i in range(320):
        seller = sellers[i % len(sellers)]
        row = (3000 + i, f'product-{i}', None, seller)
        offers.append(row)
        by_seller[seller].append(row)
    owner = {seller: users[i] for i, seller in enumerate(sellers)}
    plans = [planned_fraud_order(i, users, sellers, offers, by_seller, owner)
             for i in range(71)]
    for product in range(5):
        rows = plans[product * 5:(product + 1) * 5]
        assert len({buyer for buyer, _ in rows}) == 5
        assert {choices[0][0] for _, choices in rows} == {offers[product][0]}
    for client in range(5):
        rows = plans[25 + client * 3:28 + client * 3]
        assert {buyer for buyer, _ in rows} == {users[len(sellers) + 30 + client]}
        assert len({choices[0][0] for _, choices in rows}) == 3
        assert {next(row[3] for row in offers if row[0] == choices[0][0])
                for _, choices in rows} == {sellers[client]}
    assert len({buyer for buyer, _ in plans[40:55]}) == 5
    assert len({choices[0][0] for _, choices in plans[40:43]}) == 3
    assert len({choices[0] for _, choices in plans[65:71]}) == 6
    assert demo_product_name(0).startswith('Computadora portátil')
    assert demo_product_name(1).startswith('Teléfono inteligente')


def test_catalogo_realista_es_determinista_y_coherente():
    products = [demo_product(i) for i in range(SCALES['full'].products)]
    assert len({product.name for product in products}) == len(products)
    assert all(product.price > 0 and product.stock >= 40 for product in products)
    assert all('DEMO modelo' not in product.name for product in products)
    assert f"{demo_product(0).attributes['ram_gb']} GB de RAM" in demo_product(0).description
    assert demo_product(9).variant_attributes['talla'] in ('S', 'M', 'L', 'XL')
    assert demo_product(16).attributes['autor'] in demo_product(16).description
    assert demo_store_name(0) != demo_store_name(8)
    assert len({demo_person_name(i) for i in range(SCALES['full'].users)}) == SCALES['full'].users
    assert {category_for(i) for i in range(40)} == set(range(12))
    assert run_tags('entrega3-demo-v1') == ('ENTRE', 'entrega3')
    assert run_tags('entrega4-realista-v1') != run_tags('presentacion-equipo-v1')


def test_atributos_sinteticos_respetan_esquemas_de_categoria():
    required = (
        {'procesador', 'ram_gb', 'almacenamiento', 'pulgadas'},
        {'ram_gb', 'almacenamiento', 'camara_mp', 'pulgadas'},
        {'tipo_audio', 'conectividad'},
        {'talla', 'color', 'material', 'genero'},
        {'talla', 'color', 'material', 'corte', 'genero'},
        {'talla', 'color', 'material', 'genero'},
        set(),
        {'autor', 'isbn', 'paginas', 'editorial'},
        {'deporte'}, {'peso_g'}, {'edad_minima'}, {'uso'},
    )
    for index in range(96):
        product = demo_product(index)
        assert required[category_for(index)] <= product.attributes.keys()
        assert product.variant_attributes.keys() <= product.attributes.keys()
        assert all(isinstance(value, (str, int, float, bool)) for value in product.attributes.values())
        if category_for(index) == 5:
            assert isinstance(product.attributes['talla'], int)


def test_compras_normales_siguen_afinidad_y_no_agotan_stock_sintetico():
    offers = [(i + 1, None, None, i // 8, None, demo_product(i).price, i)
              for i in range(SCALES['full'].products)]
    sold = {row[0]: 0 for row in offers}
    for order_index in range(SCALES['full'].orders):
        buyer_index = (order_index * 17 + 7) % SCALES['full'].users
        choices = plan_normal_order(order_index, buyer_index,
                                    2 if order_index < 4000 else 1, offers)
        for offer_id, quantity in choices:
            sold[offer_id] += quantity
    assert max(sold.values()) <= 350
    assert all(sold[row[0]] <= demo_product(row[6]).stock for row in offers)


def test_un_mongo_uri_del_entorno_no_cambia_el_destino_de_la_carga(tmp_path, monkeypatch):
    # Un proceso que cargó backend/.env tiene el MONGO_URI de PRINCIPAL: no debe usarse.
    monkeypatch.setenv('MONGO_URI', 'mongodb://tiendaya_api:x@localhost:27017/tiendaya')
    config = load_demo_env(write_env(tmp_path, SAFE_ENV))
    assert ':27117/' in config['MONGO_URI']


def test_la_cuenta_del_instalador_tampoco_puede_apuntar_a_principal(tmp_path, monkeypatch):
    monkeypatch.setenv('DEMO_MONGO_URI_INSTALACION', 'mongodb://tiendaya_admin:x@localhost:27017/tiendaya')
    with pytest.raises(SystemExit):
        load_demo_env(write_env(tmp_path, SAFE_ENV))
    monkeypatch.setenv('DEMO_MONGO_URI_INSTALACION', 'mongodb://tiendaya_admin:x@127.0.0.1:27117/tiendaya_demo')
    assert load_demo_env(write_env(tmp_path, SAFE_ENV))['MONGO_URI'].startswith('mongodb://tiendaya_admin:')
