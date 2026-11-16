"""Limitador de intentos por ventana fija.

Usa Redis cuando está disponible (compartido entre procesos) y recae en memoria
local si Redis falla, para no dejar los endpoints de autenticación sin límite.
Este módulo no depende de FastAPI ni de la configuración global, para poder
probarse de forma aislada.
"""
import threading
import time

try:  # redis es opcional para pruebas unitarias
    from redis import Redis  # noqa: F401
except ImportError:  # pragma: no cover
    Redis = None

_MAX_MEMORY_KEYS = 10_000


class FixedWindowLimiter:
    def __init__(self, redis_client=None, clock=time.time):
        self._redis = redis_client
        self._clock = clock
        self._memory: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        """Registra un intento. Devuelve True si está dentro del límite."""
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("limit y window_seconds deben ser positivos")
        if self._redis is not None:
            try:
                return self._hit_redis(key, limit, window_seconds)
            except Exception:
                pass  # Redis caído: se usa el contador local del proceso
        return self._hit_memory(key, limit, window_seconds)

    def _hit_redis(self, key: str, limit: int, window_seconds: int) -> bool:
        bucket = int(self._clock() // window_seconds)
        redis_key = f"agv:rl:{key}:{bucket}"
        pipe = self._redis.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, window_seconds + 1)
        count, _ = pipe.execute()
        return int(count) <= limit

    def _hit_memory(self, key: str, limit: int, window_seconds: int) -> bool:
        bucket = int(self._clock() // window_seconds)
        with self._lock:
            if len(self._memory) > _MAX_MEMORY_KEYS:
                self._memory.clear()  # purga simple; evita crecimiento sin límite
            stored_bucket, count = self._memory.get(key, (bucket, 0))
            if stored_bucket != bucket:
                stored_bucket, count = bucket, 0
            count += 1
            self._memory[key] = (stored_bucket, count)
            return count <= limit
