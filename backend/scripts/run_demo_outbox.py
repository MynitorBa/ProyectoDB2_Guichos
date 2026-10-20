"""Run only the Outbox consumers for the existing TiendaYa DEMO.

The DEMO API is intentionally started with --lifespan off for visual review.
This process enables projections without starting flash, checkout, or fraud workers.
"""

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.services.outbox_service import start_outbox_worker, stop_outbox_worker


def main() -> None:
    if (
        settings.MYSQL_DB != 'tiendaya_demo'
        or settings.MYSQL_PORT != 3317
        or settings.MONGO_DB != 'tiendaya_demo'
        or settings.REDIS_PORT != 6389
    ):
        raise SystemExit('El Outbox de DEMO no se inicia: configuración incorrecta.')

    print('Outbox DEMO activo; los demás workers permanecen apagados.', flush=True)
    start_outbox_worker()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        stop_outbox_worker()


if __name__ == '__main__':
    main()
