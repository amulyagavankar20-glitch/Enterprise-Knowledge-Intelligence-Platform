"""Redis-backed shared rate limiting with an explicit local fallback."""

import hashlib
import logging
import os
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request
from redis import Redis
from redis.exceptions import RedisError

_requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_lock = Lock()
_WINDOW_SECONDS = 60.0
_REDIS_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""
logger = logging.getLogger(__name__)
_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
        _redis_client = Redis.from_url(
            redis_url,
            socket_connect_timeout=0.35,
            socket_timeout=0.35,
            retry_on_timeout=False,
            decode_responses=True,
        )
    return _redis_client


def _enforce_local_limit(key: tuple[str, str], *, limit: int, now: float) -> None:
    with _lock:
        events = _requests[key]
        while events and now - events[0] >= _WINDOW_SECONDS:
            events.popleft()
        if len(events) >= limit:
            raise HTTPException(status_code=429, detail="Too many requests.")
        events.append(now)

        if len(_requests) > 10_000:
            stale = [
                item for item, values in _requests.items()
                if not values or now - values[-1] >= _WINDOW_SECONDS
            ]
            for item in stale:
                _requests.pop(item, None)
            while len(_requests) > 10_000:
                _requests.pop(next(iter(_requests)))


def enforce_rate_limit(request: Request, *, scope: str, limit: int) -> None:
    client_host = request.client.host if request.client else "unknown"
    host_hash = hashlib.sha256(client_host.encode("utf-8")).hexdigest()[:20]
    redis_key = f"eki:ratelimit:v1:{scope}:{host_hash}"
    try:
        count = int(get_redis_client().eval(
            _REDIS_SCRIPT, 1, redis_key, int(_WINDOW_SECONDS)
        ))
    except RedisError as exc:
        logger.warning(
            "distributed_rate_limit_unavailable",
            extra={"error_type": type(exc).__name__, "scope": scope},
        )
        if os.getenv("RATE_LIMIT_REDIS_REQUIRED", "false").casefold() in {
            "1", "true", "yes", "on",
        }:
            raise HTTPException(
                status_code=503,
                detail="Request protection is temporarily unavailable.",
            ) from exc
        _enforce_local_limit((scope, host_hash), limit=limit, now=time.monotonic())
        return

    if count > limit:
        raise HTTPException(status_code=429, detail="Too many requests.")
