"""Subida de imágenes de reseñas: nada se escribe en disco hasta validar todo.

Cada prueba crea su propia reseña del comprador de prueba y la borra al final,
junto con sus imágenes, sus archivos y los eventos del outbox que generó.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.v1 import reviews
from app.main import app
from tests.test_checkout import TestSession, USUARIO_COMPRADOR_ID

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64
JPG = b'\xff\xd8\xff\xe0' + b'\x00' * 64


def _cliente(email: str) -> TestClient:
    c = TestClient(app, raise_server_exceptions=False)
    token = c.post('/api/v1/auth/login', json={'email': email, 'password': 'password123'}).json()['access_token']
    c.headers['Authorization'] = f'Bearer {token}'
    return c


@pytest.fixture
def resena():
    public_id = f'prueba-imagenes-{uuid4().hex[:12]}'
    with TestSession() as db:
        referencia = db.execute(text('SELECT id FROM producto_referencias ORDER BY id LIMIT 1')).scalar_one()
        db.execute(text("""
            INSERT INTO resenas (public_id, usuario_id, producto_referencia_id, calificacion, comentario,
                                 estado_moderacion, verificada_compra, version, aprobada, fecha)
            VALUES (:p, :u, :r, 5, 'Prueba de imágenes', 'pendiente', 0, 1, 0, NOW())
        """), {'p': public_id, 'u': USUARIO_COMPRADOR_ID, 'r': referencia})
        resena_id = db.execute(text('SELECT id FROM resenas WHERE public_id = :p'), {'p': public_id}).scalar_one()
        db.commit()
    yield public_id
    for archivo in reviews.STATIC_REVIEWS_DIR.glob(f'{public_id}_*'):
        archivo.unlink(missing_ok=True)
    with TestSession() as db:
        db.execute(text('DELETE FROM resena_imagenes WHERE resena_id = :r'), {'r': resena_id})
        db.execute(text("DELETE FROM outbox_eventos WHERE agregado_tipo = 'resena' AND agregado_id = :r"),
                   {'r': str(resena_id)})
        db.execute(text('DELETE FROM resenas WHERE id = :r'), {'r': resena_id})
        db.commit()


def _archivos(public_id: str) -> list[str]:
    return sorted(a.name for a in reviews.STATIC_REVIEWS_DIR.glob(f'{public_id}_*'))


def _imagenes(public_id: str) -> int:
    with TestSession() as db:
        return db.execute(text("""
            SELECT COUNT(*) FROM resena_imagenes i JOIN resenas r ON r.id = i.resena_id WHERE r.public_id = :p
        """), {'p': public_id}).scalar_one()


def _subir(c: TestClient, public_id: str, *archivos: tuple[str, bytes]):
    return c.post(f'/api/v1/reviews/{public_id}/imagenes',
                  files=[('archivos', (nombre, contenido)) for nombre, contenido in archivos])


def test_imagenes_validas_se_guardan(resena):
    respuesta = _subir(_cliente('comprador1@gmail.com'), resena, ('a.png', PNG), ('b.jpg', JPG))

    assert respuesta.status_code == 201, respuesta.text
    assert len(respuesta.json()['imagenes']) == 2
    assert len(_archivos(resena)) == 2 and _imagenes(resena) == 2


def test_mas_de_5_mb_se_rechaza_sin_escribir(resena):
    grande = PNG + b'\x00' * (5 * 1024 * 1024)

    respuesta = _subir(_cliente('comprador1@gmail.com'), resena, ('grande.png', grande))

    assert respuesta.status_code == 413
    assert _archivos(resena) == [] and _imagenes(resena) == 0


def test_extension_falseada_se_rechaza(resena):
    respuesta = _subir(_cliente('comprador1@gmail.com'), resena, ('foto.png', b'no soy una imagen'))

    assert respuesta.status_code == 400
    assert _archivos(resena) == []


def test_resena_ajena_se_rechaza_antes_de_escribir(resena):
    respuesta = _subir(_cliente('vendedor1@tiendaya.gt'), resena, ('a.png', PNG))

    assert respuesta.status_code == 404
    assert _archivos(resena) == [] and _imagenes(resena) == 0


def test_un_segundo_archivo_invalido_no_deja_huerfano_el_primero(resena):
    respuesta = _subir(_cliente('comprador1@gmail.com'), resena, ('a.png', PNG), ('b.png', b'texto'))

    assert respuesta.status_code == 400
    assert _archivos(resena) == [] and _imagenes(resena) == 0


def test_no_se_pasa_de_cuatro_imagenes(resena):
    c = _cliente('comprador1@gmail.com')
    assert _subir(c, resena, *[(f'{i}.png', PNG) for i in range(3)]).status_code == 201

    respuesta = _subir(c, resena, ('4.png', PNG), ('5.png', PNG))

    assert respuesta.status_code == 400
    assert len(_archivos(resena)) == 3 and _imagenes(resena) == 3


def test_una_falla_de_mysql_despues_de_escribir_borra_los_archivos(resena, monkeypatch):
    def falla(*args, **kwargs):
        raise RuntimeError('MySQL no respondió')
    monkeypatch.setattr(reviews.mysql_svc, 'agregar_imagenes', falla)

    respuesta = _subir(_cliente('comprador1@gmail.com'), resena, ('a.png', PNG))

    assert respuesta.status_code == 500
    assert _archivos(resena) == [] and _imagenes(resena) == 0


# ── Publicar reseña y fotos juntas (POST /reviews/publicar) ──────────────────

def _publicar(c: TestClient, campos: dict, *archivos: tuple[str, bytes]):
    return c.post('/api/v1/reviews/publicar', data=campos,
                  files=[('archivos', (nombre, contenido)) for nombre, contenido in archivos] or None)


def _resenas_del_comprador() -> int:
    with TestSession() as db:
        return db.execute(text('SELECT COUNT(*) FROM resenas WHERE usuario_id = :u'),
                          {'u': USUARIO_COMPRADOR_ID}).scalar_one()


def test_publicar_con_foto_de_mas_de_5_mb_no_publica_la_resena():
    """El caso reportado: antes la reseña quedaba publicada aunque la foto se rechazara."""
    with TestSession() as db:
        ref, vendedor = db.execute(text('SELECT producto_ref, vendedor_id FROM ofertas ORDER BY id LIMIT 1')).one()
    antes = _resenas_del_comprador()

    respuesta = _publicar(_cliente('comprador1@gmail.com'),
                          {'producto_ref': ref, 'vendedor_id': vendedor, 'calificacion': 5, 'texto': 'Excelente producto'},
                          ('grande.png', PNG + b'\x00' * (5 * 1024 * 1024)))

    assert respuesta.status_code == 413
    assert _resenas_del_comprador() == antes


@pytest.fixture
def resena_verificada():
    """Una reseña real del comprador con compra pagada; se restaura al terminar."""
    with TestSession() as db:
        fila = db.execute(text("""
            SELECT r.id, r.public_id, r.vendedor_id, pr.producto_ref, r.calificacion, r.comentario, r.version
            FROM resenas r JOIN producto_referencias pr ON pr.id = r.producto_referencia_id
            WHERE r.usuario_id = :u AND r.verificada_compra = 1
              AND NOT EXISTS (SELECT 1 FROM resena_imagenes i WHERE i.resena_id = r.id)
            ORDER BY r.id LIMIT 1"""), {'u': USUARIO_COMPRADOR_ID}).one_or_none()
    if fila is None:
        pytest.skip('El comprador de prueba no tiene una reseña verificada sin fotos.')
    yield fila
    for archivo in reviews.STATIC_REVIEWS_DIR.glob(f'{fila.public_id}_*'):
        archivo.unlink(missing_ok=True)
    with TestSession() as db:
        db.execute(text('DELETE FROM resena_imagenes WHERE resena_id = :r'), {'r': fila.id})
        db.execute(text("DELETE FROM outbox_eventos WHERE agregado_tipo = 'resena' AND agregado_id = :r AND estado = 'pendiente'"),
                   {'r': str(fila.id)})
        db.execute(text('UPDATE resenas SET calificacion = :c, comentario = :t, version = :v WHERE id = :r'),
                   {'c': fila.calificacion, 't': fila.comentario, 'v': fila.version, 'r': fila.id})
        db.commit()


def test_publicar_edicion_con_fotos_validas_guarda_todo(resena_verificada):
    r = resena_verificada
    respuesta = _publicar(_cliente('comprador1@gmail.com'),
                          {'producto_ref': r.producto_ref, 'vendedor_id': r.vendedor_id, 'calificacion': 5,
                           'texto': 'Muy bueno, lo recomiendo', 'resena_id': r.public_id},
                          ('a.png', PNG), ('b.jpg', JPG))

    assert respuesta.status_code == 201, respuesta.text
    assert len(_archivos(r.public_id)) == 2 and _imagenes(r.public_id) == 2


def test_publicar_edicion_con_una_foto_invalida_no_cambia_nada(resena):
    with TestSession() as db:
        ref = db.execute(text("""
            SELECT pr.producto_ref FROM resenas r JOIN producto_referencias pr ON pr.id = r.producto_referencia_id
            WHERE r.public_id = :p"""), {'p': resena}).scalar_one()

    respuesta = _publicar(_cliente('comprador1@gmail.com'),
                          {'producto_ref': ref, 'vendedor_id': 1, 'calificacion': 1,
                           'texto': 'Cambio de opinión', 'resena_id': resena},
                          ('a.png', PNG), ('b.png', b'no es imagen'))

    assert respuesta.status_code == 400
    with TestSession() as db:
        assert db.execute(text('SELECT calificacion FROM resenas WHERE public_id = :p'), {'p': resena}).scalar_one() == 5
    assert _archivos(resena) == [] and _imagenes(resena) == 0
