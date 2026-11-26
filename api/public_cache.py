"""Brief reuse of public browse answers, which are the same for every visitor.

Inside one Vercel deployment the catalog, reviewed photos and hours files are
read-only, so a city/date answer changes only with photo-like totals and the KST
day (facts expire by date). Reusing it for a few minutes skips the radius scan
(Seoul: about 2,500 places) and the likes database round trip.

Every copy (this process, Vercel's CDN, the browser) gets only the time the answer
has left, capped at the next KST midnight, so no visitor sees an answer older
than PUBLIC_BROWSE_CACHE_S seconds or one computed on an earlier day.
An answer that touched the likes store's outage cooldown is neither kept nor
shared, so covers return to like order as soon as the store recovers.

Local runs and tests rewrite data files between requests, so in-process reuse is
off unless the process runs on Vercel or PUBLIC_BROWSE_CACHE_S is set; setting it
to 0 also stops CDN and browser sharing.
"""
from collections import OrderedDict
from datetime import datetime, time as clock_time, timedelta
import os
import threading
import time
from zoneinfo import ZoneInfo

from . import photo_likes
from .observability import shared as shared_policy
from .scoring_cache import catalog_version
from pipeline.catalog_visitors import today as kst_today

DEFAULT_SECONDS = 300
BROWSER_SECONDS = 60    # Long enough for the page's <link rel="preload"> answer to be reused by the app's fetch.
MAX_ENTRIES = 256
KST = ZoneInfo('Asia/Seoul')


def _configured():
    raw = os.environ.get('PUBLIC_BROWSE_CACHE_S')
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


def ttl_seconds() -> float:
    """In-process reuse window: on by default only on Vercel."""
    configured = _configured()
    if configured is not None:
        return configured
    return DEFAULT_SECONDS if os.environ.get('VERCEL') else 0.0


def share_seconds() -> float:
    """CDN/browser window for a freshly computed answer; 0 only when explicitly disabled."""
    configured = _configured()
    return DEFAULT_SECONDS if configured is None else configured


def seconds_until_kst_midnight(now=None) -> int:
    now = now or datetime.now(KST)
    midnight = datetime.combine(now.date() + timedelta(days=1), clock_time(0), KST)
    return int((midnight - now).total_seconds())


def likes_degraded() -> bool:
    """Configured likes store inside its failure cooldown: covers fall back to curated order."""
    return photo_likes.configured() and not photo_likes.available()


class TTLCache:
    def __init__(self, max_entries=MAX_ENTRIES, clock=time.monotonic):
        self.max_entries, self.clock = max_entries, clock
        self._items: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        """(seconds left, value) for a live entry, else None."""
        with self._lock:
            hit = self._items.get(key)
            if hit is None:
                return None
            expires, value = hit
            left = expires - self.clock()
            if left <= 0:
                del self._items[key]
                return None
            self._items.move_to_end(key)
            return left, value

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
    """compute() once per key and window; let the CDN and browser keep it only for the time it has left.

    The key gains today's KST date and the catalog file identity, so a new day or a
    replaced catalog never reuses an older answer. Exceptions (404s) are not kept.
    """
    full_key = (*key, kst_today(), catalog_version())
    ttl = ttl_seconds()
    hit = _cache.get(full_key) if ttl else None
    if hit is not None:
        left, value = hit
    else:
        # Checked before and after: a read skipped during the cooldown must not be kept
        # even when the cooldown ends while the answer is being built.
        degraded = likes_degraded()
        value = compute()
        if degraded or likes_degraded():
            return value
        left = ttl if ttl else share_seconds()
        if ttl:
            _cache.put(full_key, value, ttl)
    lifetime = min(int(left), seconds_until_kst_midnight())
    response.headers['Cache-Control'] = shared_policy(lifetime, max_age=min(BROWSER_SECONDS, lifetime))
    return value
