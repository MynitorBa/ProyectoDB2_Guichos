"""Run only the checkout recovery worker for the existing TiendaYa DEMO.

The DEMO API is started with --lifespan off, so its startup hook (which
launches the reconciler and the reaper) never runs. Without this process a
payment left «en verificación» (gateway timeout or 503) is never resolved.
This process starts only the checkout recovery loop; flash and fraud workers
stay off, exactly like run_demo_outbox.py does for projections.
"""

import logging
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.services.checkout_recovery_worker import (
    start_checkout_recovery_worker, stop_checkout_recovery_worker,
)


def main() -> None:
    # Sin esto, los logger.info del reconciliador no aparecen en recovery.out.log.
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    if (
        settings.MYSQL_DB != 'tiendaya_demo'
        or settings.MYSQL_PORT != 3317
        or settings.MONGO_DB != 'tiendaya_demo'
        or settings.REDIS_PORT != 6389
    ):
        raise SystemExit('La recuperación del checkout de DEMO no se inicia: configuración incorrecta.')

    print(
        f'Recuperación del checkout DEMO activa: cada {settings.RECONCILIADOR_INTERVALO_S} s, '
        f'gracia {settings.RECONCILIADOR_GRACIA_S} s, pasarela {settings.PAYMENT_GATEWAY_URL}.',
        flush=True,
    )
    start_checkout_recovery_worker()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        stop_checkout_recovery_worker()


if __name__ == '__main__':
    main()
