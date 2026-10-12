"""Per-client-IP sliding-window limits for public, unauthenticated endpoints.

State lives in this process's memory: each uvicorn worker or serverless instance
counts separately, so the effective limit is (limit x processes). This is abuse
damping, not a quota; put a shared limiter (proxy/WAF) in front for hard limits.
"""
from __future__ import annotations

import math
import os
import threading
import time
from collections import deque


class SlidingWindow:
    def __init__(self, limit: int, window_s: float = 60.0, clock=time.monotonic, max_keys: int = 10_000):
        self.limit, self.window, self.clock, self.max_keys = limit, window_s, clock, max_keys
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> float | None:
        """Record a request; returns seconds to wait when over the limit, else None."""
        if self.limit <= 0:
            return None
        now = self.clock()
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                if len(self._hits) >= self.max_keys:
                    self._prune(now)
                hits = self._hits[key] = deque()
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return max(0.0, hits[0] + self.window - now)
            hits.append(now)
            return None

    def _prune(self, now: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window]:
            del self._hits[key]
        while len(self._hits) >= self.max_keys:          # Still full: drop the oldest entries.
            del self._hits[next(iter(self._hits))]


def per_minute(env: str, default: int) -> SlidingWindow:
    return SlidingWindow(int(os.environ.get(env, str(default))))


def client_ip(request) -> str:
    # Vercel overwrites X-Forwarded-For with the real client; elsewhere run uvicorn
    # with --proxy-headers behind a trusted proxy so request.client is the client.
    if os.environ.get('VERCEL') == '1':
        forwarded = request.headers.get('x-real-ip') or request.headers.get('x-forwarded-for', '').split(',')[0]
        if forwarded.strip():
            return forwarded.strip()
    return request.client.host if request.client else 'unknown'


def retry_after(request, rules) -> int | None:
    """rules: [(path prefix, SlidingWindow)]. Returns Retry-After seconds when limited."""
    if request.method == 'OPTIONS':
        return None                                     # CORS preflight carries no work.
    path = request.url.path
    for prefix, limiter in rules:
        if path.startswith(prefix):
            wait = limiter.hit(prefix + '|' + client_ip(request))
            if wait is not None:
                return max(1, math.ceil(wait))
    return None
