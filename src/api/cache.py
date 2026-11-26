"""Small in-memory TTL cache shared by the NBA data modules.

NBA servers occasionally answer with an empty or non-JSON body, and when a client
sends too many requests its CDN starts answering every request with a 403 HTML
page. So a failed fetch is retried once, then remembered for ERROR_BACKOFF
seconds: during that time the last good value is served if there is one, and the
NBA servers are not asked again.
"""
import json
import time

ERROR_BACKOFF = 60

_cache = {}
_failures = {}


class NBAUnavailable(Exception):
    """An NBA request failed; the message is meant for players to read."""


def describe(error):
    if isinstance(error, NBAUnavailable):
        return str(error)
    if isinstance(error, json.JSONDecodeError):
        return "NBA 伺服器拒絕連線或沒有回傳資料（可能暫時封鎖了這台電腦的 IP），請稍後再試"
    return f"NBA 資料取得失敗：{error}"


def cached(key, ttl_for, fetch):
    """Return the cached value for `key`, or call `fetch()` and keep it for `ttl_for(value)` seconds."""
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    failure = _failures.get(key)
    if failure and failure[0] > now:
        if hit:
            return hit[1]
        raise NBAUnavailable(failure[1])
    try:
        value = with_retry(fetch)
    except Exception as e:
        message = describe(e)
        _failures[key] = (now + ERROR_BACKOFF, message)
        if hit:
            return hit[1]  # stale data beats an error page
        raise NBAUnavailable(message) from e
    _failures.pop(key, None)
    _cache[key] = (time.monotonic() + ttl_for(value), value)
    return value


def with_retry(fetch, attempts=2):
    """Call `fetch()`, retrying once after a short pause."""
    for attempt in range(attempts):
        try:
            return fetch()
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(0.5)
