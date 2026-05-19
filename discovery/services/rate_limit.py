from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest


class RateLimitExceeded(Exception):
    pass


def _client_ip(request: HttpRequest) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown") or "unknown"


def check_rate_limit(request: HttpRequest) -> None:
    limit = int(getattr(settings, "SEARCH_RATE_LIMIT_PER_MIN", 20))
    if limit <= 0:
        return
    ip = _client_ip(request)
    key = f"discovery:rl:{ip}"
    broker = getattr(settings, "CELERY_BROKER_URL", "") or ""
    if not broker.startswith("redis://"):
        return
    try:
        import redis
    except ImportError:
        return
    try:
        client = redis.from_url(broker)
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, 60)
        count, _ = pipe.execute()
        if int(count) > limit:
            raise RateLimitExceeded(f"요청이 너무 많습니다. 분당 {limit}회까지 가능합니다.")
    except RateLimitExceeded:
        raise
    except Exception:
        return
