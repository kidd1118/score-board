"""Small in-memory TTL cache with one retry, shared by the NBA data modules."""
import time

_cache = {}


def cached(key, ttl_for, fetch):
    """Return the cached value for `key`, or call `fetch()` and keep it for `ttl_for(value)` seconds."""
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    value = with_retry(fetch)
    _cache[key] = (time.monotonic() + ttl_for(value), value)
    return value


def with_retry(fetch, attempts=2):
    """NBA servers occasionally answer with an empty or non-JSON body; one retry usually fixes it."""
    for attempt in range(attempts):
        try:
            return fetch()
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(0.5)
