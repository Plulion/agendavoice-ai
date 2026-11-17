"""Fixed-window rate limiter with Redis primary storage and in-memory fallback.

Uses Redis when available (shared across worker processes) and falls back to
process-local memory if Redis is unreachable so authentication endpoints remain
protected. Kept free of FastAPI/global settings dependencies for isolated unit testing.
"""
import threading
import time

try:  # redis is optional during standalone unit testing
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
        """Record an attempt and return True if within the allowed window limit."""
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("limit and window_seconds must be positive")
        if self._redis is not None:
            try:
                return self._hit_redis(key, limit, window_seconds)
            except Exception:
                pass  # Redis unavailable: fall back to process-local counter
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
                self._memory.clear()  # Simple cap to prevent unbounded memory growth
            stored_bucket, count = self._memory.get(key, (bucket, 0))
            if stored_bucket != bucket:
                stored_bucket, count = bucket, 0
            count += 1
            self._memory[key] = (stored_bucket, count)
            return count <= limit
