"""Sliding-window limits: verified accounts, otherwise public client IPs.

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

    def hit(self, key: str, limit: int | None = None) -> float | None:
        """Record a request; returns seconds to wait when over the limit, else None."""
        limit = self.limit if limit is None else limit
        if limit <= 0:
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
            if len(hits) >= limit:
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


def per_day(env: str, default: int) -> SlidingWindow:
    return SlidingWindow(int(os.environ.get(env, str(default))), window_s=86400.0)


def authenticated_ip_factor() -> int:
    """Verified accounts count separately, but one address still gets at most
    this multiple of the per-user limit across all its accounts (0 disables)."""
    return int(os.environ.get('RATE_LIMIT_IP_FACTOR', '4'))


def trusted_ips() -> set[str]:
    return {ip.strip() for ip in os.environ.get('FORWARDED_ALLOW_IPS', '').split(',') if ip.strip()}


def trusted_proxy(peer: str | None) -> bool:
    """Only a known proxy may describe the client via X-Forwarded-* headers.

    Vercel terminates TLS and overwrites these headers itself; elsewhere list the
    proxy addresses in FORWARDED_ALLOW_IPS (uvicorn --proxy-headers reads the same).
    """
    if os.environ.get('VERCEL') == '1':
        return True
    trusted = trusted_ips()
    return '*' in trusted or (peer is not None and peer in trusted)


def peer_ip(request) -> str:
    return request.client.host if request.client else 'unknown'


def forwarded_scheme(request) -> str:
    """The browser-facing scheme: X-Forwarded-Proto from a trusted proxy, else the socket's."""
    proto = request.headers.get('x-forwarded-proto', '').split(',')[0].strip().lower()
    if proto in ('http', 'https') and trusted_proxy(peer_ip(request)):
        return proto
    return str(request.url.scheme)


def client_ip(request) -> str:
    peer = peer_ip(request)
    if not trusted_proxy(peer):
        return peer                                  # Client-supplied headers are ignored.
    if os.environ.get('VERCEL') == '1':
        real = request.headers.get('x-real-ip', '').strip()
        if real:
            return real
    trusted = trusted_ips()
    hops = [hop.strip() for hop in request.headers.get('x-forwarded-for', '').split(',') if hop.strip()]
    # Right-most hop not appended by a trusted proxy; anything further left came from the client.
    for hop in reversed(hops):
        if hop not in trusted:
            return hop
    return peer


def retry_after(request, rules, user_id: str | None = None) -> int | None:
    """rules: [(path prefix, SlidingWindow)]. Returns Retry-After seconds when limited."""
    if request.method == 'OPTIONS':
        return None                                     # CORS preflight carries no work.
    path = request.url.path
    for prefix, limiter in rules:
        if path.startswith(prefix):
            # Login/refresh always retain their separate IP abuse limit. Never
            # use unverified JWT claims, token strings or client-supplied IDs.
            ip = 'ip:' + client_ip(request)
            if user_id and prefix == '/v1/':
                wait = limiter.hit(prefix + '|user:' + user_id)
                if wait is None:
                    wait = limiter.hit(prefix + '|accounts|' + ip, limit=limiter.limit * authenticated_ip_factor())
            else:
                wait = limiter.hit(prefix + '|' + ip)
            if wait is not None:
                return max(1, math.ceil(wait))
    return None
