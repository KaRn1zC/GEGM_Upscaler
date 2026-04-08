"""Pool de connexions Redis async partagé par l'application.

Fournit un singleton ``redis.asyncio.Redis`` initialisé paresseusement
au premier appel et fermé proprement via le lifespan FastAPI.
"""

from redis.asyncio import Redis

from app.core.config import settings

_redis: Redis | None = None


def get_redis_pool() -> Redis:
    """Retourne l'instance Redis partagée, en la créant si nécessaire.

    Le pool est thread-safe et utilise des connexions multiplexées par
    défaut (``decode_responses=True`` pour manipuler directement des ``str``).

    Returns:
        Instance ``redis.asyncio.Redis`` prête à l'emploi.
    """
    global _redis
    if _redis is None:
        _redis = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
    return _redis


async def close_redis_pool() -> None:
    """Ferme proprement le pool Redis.

    À appeler dans le lifespan shutdown de FastAPI pour libérer les
    connexions réseau.
    """
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
