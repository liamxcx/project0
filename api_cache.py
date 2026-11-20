import logging

import redis

from config import REDIS_URL

log = logging.getLogger("api_cache")

# Todas las claves de la caché de la API empiezan así. La espera del botón de
# actualizar no, así que vaciar la caché no la borra.
PREFIX = "cache:"


def clear_api_cache():
    """Borra las respuestas cacheadas por la API. Si Redis falla, sigue adelante."""
    client = redis.Redis.from_url(REDIS_URL, socket_timeout=1)
    try:
        keys = list(client.scan_iter(match=f"{PREFIX}*"))
        if keys:
            client.delete(*keys)
    except redis.RedisError as error:
        log.warning("No se ha podido vaciar la caché de la API: %s", error)
        return 0
    return len(keys)
