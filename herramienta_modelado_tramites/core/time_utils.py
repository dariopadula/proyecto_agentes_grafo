from datetime import datetime
from datetime import timezone
from datetime import timedelta


MONTEVIDEO_TZ = timezone(timedelta(hours=-3))


def now_iso() -> str:
    """Devuelve una marca temporal ISO simple para trazabilidad local."""
    return datetime.now(MONTEVIDEO_TZ).isoformat(timespec="seconds")
