"""Operations plumbing shared by the preview and the account API.

JSON logs on stdout, Sentry only when SENTRY_DSN is set, a health payload with
the likes store's reachability, and pure-ASGI response hygiene (Cache-Control,
selective gzip). Nothing here reads request bodies, query strings or cookies:
preview inputs include birth data and the account API takes lat/lng as query
parameters, so Sentry events are scrubbed of query strings before they leave.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time

from starlette.datastructures import MutableHeaders
from starlette.middleware.gzip import GZipMiddleware

log = logging.getLogger('photospot.http')
NO_STORE = 'no-store'
IMMUTABLE = 'public, max-age=31536000, immutable'
PUBLIC_HOUR = 'public, max-age=3600'


class JsonFormatter(logging.Formatter):
    """One JSON object per line; `extra={'http': {...}}` fields are merged in."""

    def format(self, record):
        entry = {'ts': time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(record.created)) + f'.{int(record.msecs):03d}Z',
                 'level': record.levelname, 'logger': record.name, 'msg': record.getMessage()}
        entry.update(getattr(record, 'http', None) or {})
        if record.exc_info:
            entry['exc'] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging():
    """Structured stdout logging once per process; LOG_LEVEL defaults to INFO."""
    root = logging.getLogger()
    if any(getattr(handler, 'photospot_json', False) for handler in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.photospot_json = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(os.environ.get('LOG_LEVEL', 'INFO').upper())
    # HTTP client libraries log full request URLs (query strings) at INFO.
    for name in ('httpx', 'httpx2', 'httpcore', 'httpcore2', 'urllib3'):
        logging.getLogger(name).setLevel(logging.WARNING)


def scrub_request(event, hint=None):
    """Sentry before_send: 요청 쿼리스트링과 URL의 쿼리를 지운다 (GET /v1/recommendations의 lat·lng).

    SDK는 send_default_pii=False여도 query_string을 모든 이벤트에 붙인다; 본문·쿠키·IP는 옵션이 막는다.
    """
    request = event.get('request')
    if request:
        request.pop('query_string', None)
        if request.get('url'):
            request['url'] = request['url'].split('?', 1)[0]
    return event


def sentry_options(mode):
    return {'environment': os.environ.get('SENTRY_ENVIRONMENT') or os.environ.get('VERCEL_ENV') or os.environ.get('APP_ENV', 'development'),
            'release': os.environ.get('VERCEL_GIT_COMMIT_SHA') or None,
            'traces_sample_rate': float(os.environ.get('SENTRY_TRACES_SAMPLE_RATE', '0')),
            # Never ship bodies (birth inputs), cookies (voter token), client IPs or query strings (coordinates).
            'send_default_pii': False, 'max_request_body_size': 'never', 'server_name': mode,
            'before_send': scrub_request, 'before_send_transaction': scrub_request}


def init_sentry(mode):
    """Error tracking only with SENTRY_DSN; the SDK is otherwise never imported."""
    dsn = os.environ.get('SENTRY_DSN')
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        logging.getLogger(__name__).warning('SENTRY_DSN is set but sentry-sdk is not installed')
        return False
    sentry_sdk.init(dsn=dsn, integrations=[StarletteIntegration(transaction_style='endpoint'),
                                           FastApiIntegration(transaction_style='endpoint')],
                    **sentry_options(mode))
    return True


def setup(mode):
    configure_logging()
    return init_sentry(mode)


def health(mode):
    """{ok, mode, catalog_version, likes:{configured, reachable}}; no connection strings."""
    from pipeline.place_catalog import metadata
    from . import photo_likes
    info = metadata()
    return {'ok': bool(info['count']), 'mode': mode, 'catalog_version': info['fetched_at'],
            'likes': {'configured': photo_likes.configured(), 'reachable': photo_likes.probe(timeout=1.0)}}


def cache_control(path, content_type=''):
    """Hashed bundles cache forever; API responses, HTML and health never; SEO files an hour."""
    if path.startswith(('/_expo/static/', '/assets/')):
        return IMMUTABLE
    if path.startswith(('/preview/', '/v1/')) or path == '/health' or content_type.startswith('text/html'):
        return NO_STORE
    if path in ('/robots.txt', '/sitemap.xml'):
        return PUBLIC_HOUR
    return None


class ResponseHeaders:
    """Cache-Control by path/type plus fixed security headers on every response."""

    def __init__(self, app, headers=None):
        self.app = app
        self.headers = headers if headers is not None else {'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer'}

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message['type'] == 'http.response.start':
                headers = MutableHeaders(scope=message)
                for key, value in self.headers.items():
                    headers[key] = value
                policy = cache_control(scope['path'], headers.get('content-type', ''))
                if policy:
                    headers['Cache-Control'] = policy
            await send(message)

        await self.app(scope, receive, send_with_headers)


class SelectiveGZip:
    """Innermost middleware so GZip sees whole bodies and its minimum_size applies.

    Token responses are excluded: compressing attacker-influenced input next to
    a secret leaks it through the response length (BREACH).
    """

    def __init__(self, app, exclude=('/v1/auth/',), minimum_size=1000, compresslevel=5):
        self.app, self.exclude = app, tuple(exclude)
        self.gzip = GZipMiddleware(app, minimum_size=minimum_size, compresslevel=compresslevel)

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http' and scope['path'].startswith(self.exclude):
            return await self.app(scope, receive, send)
        await self.gzip(scope, receive, send)


class RequestLog:
    """Access log as JSON (method, path, status, ms); never query strings or bodies.

    LOG_REQUESTS=0 silences successes; failures (status >= 500) are always logged.
    """

    def __init__(self, app, service):
        self.app, self.service = app, service

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        started, status = time.monotonic(), {'code': 0}

        async def observe(message):
            if message['type'] == 'http.response.start':
                status['code'] = message['status']
            await send(message)

        try:
            await self.app(scope, receive, observe)
        finally:
            code = status['code'] or 500
            if code >= 500 or os.environ.get('LOG_REQUESTS', '1') != '0':
                log.log(logging.ERROR if code >= 500 else logging.INFO, 'request',
                        extra={'http': {'service': self.service, 'method': scope['method'], 'path': scope['path'],
                                        'status': code, 'ms': round((time.monotonic() - started) * 1000)}})
