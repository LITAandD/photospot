"""Brief reuse of public browse answers, which are the same for every visitor.

Inside one Vercel deployment the catalog, reviewed photos and hours files are
read-only, so a city/date answer changes only with photo-like totals. Reusing it
for a few minutes skips the radius scan (Seoul: about 2,500 places) and the likes
database round trip. Local runs and tests rewrite those files between requests,
so reuse is off unless the process runs on Vercel or PUBLIC_BROWSE_CACHE_S is set.
An answer built while the likes store is in its outage cooldown is neither kept
nor shared, so covers return to like order as soon as the store recovers.
"""
from collections import OrderedDict
import os
import threading
import time

from . import photo_likes
from .observability import SHARED_BROWSE_DATA
from .scoring_cache import catalog_version
from pipeline.catalog_visitors import today as kst_today

DEFAULT_SECONDS = 300   # Same window as the CDN's s-maxage in SHARED_BROWSE_DATA.
MAX_ENTRIES = 256


def ttl_seconds() -> float:
    raw = os.environ.get('PUBLIC_BROWSE_CACHE_S')
    if raw is not None:
        try:
            return max(0.0, float(raw))
        except ValueError:
            return 0.0
    return DEFAULT_SECONDS if os.environ.get('VERCEL') else 0.0


def likes_degraded() -> bool:
    """Configured likes store inside its failure cooldown: covers fell back to curated order."""
    return photo_likes.configured() and not photo_likes.available()


class TTLCache:
    def __init__(self, max_entries=MAX_ENTRIES, clock=time.monotonic):
        self.max_entries, self.clock = max_entries, clock
        self._items: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            hit = self._items.get(key)
            if hit is None:
                return None
            expires, value = hit
            if expires <= self.clock():
                del self._items[key]
                return None
            self._items.move_to_end(key)
            return value

    def put(self, key, value, ttl):
        with self._lock:
            self._items[key] = (self.clock() + ttl, value)
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)

    def clear(self):
        with self._lock:
            self._items.clear()


_cache = TTLCache()


def shared(response, key, compute):
    """compute() once per key and window; mark the reply CDN-shareable when it is healthy.

    The key gains today's KST date and the catalog file identity, so a new day or a
    replaced catalog never reuses an older answer. Exceptions (404s) are not kept.
    """
    full_key = (*key, kst_today(), catalog_version())
    ttl = ttl_seconds()
    value = _cache.get(full_key) if ttl else None
    if value is None:
        value = compute()
        if likes_degraded():
            return value
        if ttl:
            _cache.put(full_key, value, ttl)
    response.headers['Cache-Control'] = SHARED_BROWSE_DATA
    return value
