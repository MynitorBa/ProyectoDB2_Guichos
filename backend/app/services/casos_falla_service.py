"""Casos de falla específicos del laboratorio de consistencia.

Cada caso responde a una pregunta concreta, como «¿qué pasa si Redis se cae
justo cuando presiono Comprar?». Preparar un caso deja el entorno limpio
(ningún otro punto activo y la pasarela aprobando) y arma, para una sola vez,
los puntos de falla que lo provocan; la siguiente acción del usuario en la
tienda lo dispara. Lo que debe ocurrir está escrito en ``esperado`` y lo
comprueba la prueba de integración citada en ``prueba``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import httpx

from app.core import fault_injection
from app.core.config import settings


@dataclass(frozen=True)
class Caso:
    id: str
    pregunta: str
    momento: str
    componente: str
    puntos: tuple[str, ...]
    como_probar: str
    esperado: tuple[str, ...]
    prueba: str


ARCHIVO_PRUEBAS = 'backend/tests/test_casos_falla.py'

CASOS: tuple[Caso, ...] = (
    Caso(
        'C01', '¿Qué pasa si Redis se cae justo cuando presiono «Comprar»?',
        'Al presionar Comprar', 'Redis', ('checkout.redis_leer_carrito',),
        'Agrega un producto al carrito, ve al checkout y presiona «Confirmar pedido».',
        ('El checkout lee el carrito de su copia en MySQL, sin esperar a Redis.',
         'La compra se confirma normalmente (HTTP 201) y se cobra una sola vez.',
         'El carrito queda vacío; al volver Redis se reconstruye desde MySQL.'),
        'test_c01_redis_cae_al_leer_el_carrito'),
    Caso(
        'C02', '¿Qué pasa si MySQL deja de responder justo al recibir mi compra?',
        'Al presionar Comprar', 'MySQL', ('checkout.mysql_al_recibir',),
        'Agrega un producto al carrito y confirma el pedido.',
        ('No se reserva ni se cobra nada mientras MySQL no responde.',
         'La compra queda en cola (HTTP 202 ORDER_QUEUED) y se ve en «Mis pedidos».',
         'Cuando MySQL vuelve (unos 15 s), la cola la procesa con la saga normal y se cobra una vez.'),
        'test_c02_mysql_no_responde_al_recibir_la_compra'),
    Caso(
        'C03', '¿Qué pasa si MySQL se cae a mitad de la reserva, con el inventario bloqueado?',
        'Durante la reserva (T1)', 'MySQL', ('checkout.mysql_durante_reserva',),
        'Agrega un producto al carrito y confirma el pedido.',
        ('La transacción se deshace entera: no queda pedido, reserva ni movimiento de inventario.',
         'Nada se cobró; la compra pasa a la cola (HTTP 202) en vez de mostrar un error.',
         'La cola la procesa cuando MySQL vuelve; el stock y los invariantes quedan correctos.'),
        'test_c03_mysql_cae_a_mitad_de_la_reserva'),
    Caso(
        'C04', '¿Qué pasa si otra compra bloquea las mismas filas en el mismo instante (deadlock)?',
        'Durante la reserva (T1)', 'MySQL', ('checkout.mysql_deadlock',),
        'Agrega un producto al carrito y confirma el pedido.',
        ('MySQL elige la compra como víctima del deadlock; la reserva se reintenta sola.',
         'El cliente no nota nada: la compra se confirma (HTTP 201) con un solo pedido y un solo cobro.',
         'Si el conflicto persiste en los 3 intentos, responde 409 CONCURRENT_UPDATE sin dejar nada a medias.'),
        'test_c04_deadlock_al_reservar_se_reintenta'),
    Caso(
        'C05', '¿Qué pasa si se pierde la respuesta justo después de pagar y vuelvo a presionar «Comprar»?',
        'Después de cobrar', 'Red / navegador', ('checkout.respuesta_perdida',),
        'Confirma el pedido; verás «Sin respuesta del servidor». Presiona «Reintentar».',
        ('El pedido ya estaba confirmado y cobrado cuando se perdió la respuesta.',
         'El navegador reintenta con la misma clave de idempotencia.',
         'Recibe el mismo pedido («ya se había registrado»): ni pedido duplicado ni cobro doble.'),
        'test_c05_respuesta_perdida_y_reintento'),
    Caso(
        'C06', '¿Qué pasa si Redis se cae justo al vaciar el carrito, con la venta ya confirmada?',
        'Después de confirmar', 'Redis', ('checkout.redis_vaciar_carrito',),
        'Agrega un producto al carrito y confirma el pedido.',
        ('La compra se muestra como exitosa: una falla de limpieza nunca se convierte en un error.',
         'Lo comprado ya salió de la copia del carrito en MySQL en la misma transacción.',
         'El evento «carrito.limpiar» del outbox lo retira de Redis; lo comprado no reaparece.'),
        'test_c06_redis_cae_al_vaciar_el_carrito'),
    Caso(
        'C07', '¿Qué pasa si Redis se cae justo al cerrar mi reserva flash, con la venta ya hecha?',
        'Después de confirmar', 'Redis', ('checkout.redis_consumir_flash',),
        'Reserva una unidad de una oferta flash y cómprala.',
        ('La compra se confirma; la venta flash ya está en MySQL (reserva «convertida»).',
         'El evento «flash.consumir» del outbox cierra la reserva en Redis.',
         'La unidad vendida no vuelve al cupo: no hay sobreventa.'),
        'test_c07_redis_cae_al_cerrar_la_reserva_flash'),
    Caso(
        'C08', '¿Qué pasa si Redis se cae justo al validar mi reserva flash al comprar?',
        'Al presionar Comprar', 'Redis', ('checkout.redis_validar_flash',),
        'Reserva una unidad de una oferta flash y cómprala.',
        ('La reserva se valida contra MySQL, la fuente durable.',
         'La compra se confirma al precio promocional reservado.',
         'El cupo de la promoción cuadra: vendidas + reservadas + libres = total.'),
        'test_c08_redis_cae_al_validar_la_reserva_flash'),
    Caso(
        'C09', '¿Qué pasa si MongoDB se cae justo al armar las líneas del pedido?',
        'Durante la reserva (T1)', 'MongoDB', ('checkout.mongo_lineas',),
        'Agrega un producto al carrito y confirma el pedido.',
        ('El nombre de cada producto sale de la copia del catálogo en MySQL.',
         'La compra se confirma con los nombres correctos (no con el SKU).',
         'La proyección del catálogo se pone al día por el outbox.'),
        'test_c09_mongo_cae_al_armar_las_lineas'),
    Caso(
        'C10', '¿Qué pasa si Redis se cae justo al agregar un producto al carrito?',
        'Al agregar al carrito', 'Redis', ('carrito.redis_agregar',),
        'Abre un producto y presiona «Agregar al carrito».',
        ('El producto se guarda en la copia del carrito en MySQL (HTTP 201).',
         'El carrito lo muestra de inmediato y se puede comprar.',
         'Al volver Redis, el carrito se reconstruye con ese producto.'),
        'test_c10_redis_cae_al_agregar_al_carrito'),
    Caso(
        'C11', '¿Qué pasa si Redis aparta mi unidad flash pero se cae antes de responder?',
        'Al reservar una oferta flash', 'Redis', ('flash.redis_tras_reservar',),
        'Abre una oferta flash activa y presiona «Reservar».',
        ('La reserva se hace en MySQL con bloqueo de fila; el usuario la recibe igual.',
         'La unidad que quedó apartada en Redis no cuenta dos veces: la promoción se reconstruye desde MySQL.',
         'El cupo cuadra: una sola reserva para el usuario, sin unidades perdidas.'),
        'test_c11_redis_reserva_flash_y_no_responde'),
    Caso(
        'C12', '¿Qué pasa si el servicio de embeddings se cae justo cuando busco?',
        'Al buscar', 'Embeddings', ('busqueda.embeddings',),
        'Busca en la tienda una frase nueva de 4 letras o más (por ejemplo «audífonos para correr»).',
        ('La búsqueda responde igual, solo con la parte de texto (semantica: false).',
         'El circuito del servicio se abre: las búsquedas siguientes no esperan su timeout.',
         'Pasados unos 15 s se vuelve a intentar y, si responde, la búsqueda es híbrida otra vez.'),
        'test_c12_embeddings_caen_al_buscar'),
)

_POR_ID = {caso.id: caso for caso in CASOS}


def listar() -> list[dict]:
    puntos = {p['punto']: p for p in fault_injection.estado()['puntos']}
    return [
        {
            **asdict(caso),
            'prueba': f'{ARCHIVO_PRUEBAS}::{caso.prueba}',
            'armado': any(puntos[p]['modo'] for p in caso.puntos),
            'disparos': sum(puntos[p]['disparos'] for p in caso.puntos),
        }
        for caso in CASOS
    ]


def preparar(caso_id: str) -> dict:
    """Deja el entorno limpio y arma los puntos del caso para una sola vez."""
    caso = _POR_ID.get(caso_id)
    if caso is None:
        raise LookupError(f'Caso desconocido: {caso_id}')
    fault_injection.desactivar()
    # Un caso a la vez y con la pasarela aprobando: el resultado depende solo de la falla del caso.
    httpx.post(f'{settings.PAYMENT_GATEWAY_URL}/control',
               json={'modo': 'aprobar', 'latencia_ms': 0, 'demora_timeout_s': 8.0}, timeout=3).raise_for_status()
    for punto in caso.puntos:
        fault_injection.activar(punto, 'una_vez')
    return next(c for c in listar() if c['id'] == caso_id)
