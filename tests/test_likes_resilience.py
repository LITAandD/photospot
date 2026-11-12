"""The likes store is an accessory: outages degrade likes, never recommendations.

Also covers the operational plumbing around it: health details, analytics
events, response caching/compression, proxy-aware rate limiting and logging.
"""
import asyncio
import json
import logging
from pathlib import Path
import socket
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from psycopg_pool import PoolTimeout

from api import analytics_routes, observability, photo_likes as likes, rate_limit
from api.config import Settings
from api.main import create_app
from api.preview import app, likes_database_error
from api.rate_limit import SlidingWindow

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fixture_catalog(tmp_path, monkeypatch):
    from scripts.load_catalog_fixture import main
    monkeypatch.setenv('PLACE_CATALOG_DB', str(tmp_path / 'catalog.sqlite3'))
    main()


@pytest.fixture
def store(monkeypatch):
    """Point the likes store at a DSN for one test; pools are closed afterwards."""
    monkeypatch.setitem(likes._state, 'outage_until', 0.0)
    monkeypatch.setitem(likes._state, 'logged_at', 0.0)
    monkeypatch.setenv('PHOTO_LIKES_COOKIE_SECRET', 'test-only-cookie-secret-' * 3)
    used = []

    def use(dsn):
        monkeypatch.setenv('PHOTO_LIKES_DATABASE_URL', dsn)
        used.append(dsn)
    yield use
    for dsn in used:
        likes.pool(dsn).close()
    likes.pool.cache_clear()


@pytest.fixture
def closed_endpoint():
    probe = socket.socket()
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
    probe.close()
    return f'postgresql://u:p@127.0.0.1:{port}/db'


@pytest.fixture
def stalled_endpoint():
    # Accepts TCP but never speaks PostgreSQL: a Neon cold start or a black-holed route.
    server = socket.socket()
    server.bind(('127.0.0.1', 0))
    server.listen(1)
    yield f'postgresql://u:p@127.0.0.1:{server.getsockname()[1]}/db'
    server.close()


def first_cover(response):
    return next(i for i in response.json()['recommendations']['items'] if i['cover_photo'])


@pytest.mark.parametrize('kind', ['closed', 'stalled'])
def test_recommendations_degrade_instead_of_failing_when_the_store_is_unreachable(
        kind, fixture_catalog, store, closed_endpoint, stalled_endpoint, caplog):
    store(stalled_endpoint if kind == 'stalled' else closed_endpoint)
    body = {'visit_date': '2026-10-10'}
    with TestClient(app) as client, caplog.at_level(logging.WARNING, logger='api.photo_likes'):
        started = time.monotonic()
        response = client.post('/preview/evaluate', json=body)
        assert response.status_code == 200 and time.monotonic() - started < 3, response.text
        cover = first_cover(response)['cover_photo']
        assert cover['likes_enabled'] is False and cover['like_count'] == 0
        pid = first_cover(response)['place_id']
        # Cooldown: the detail request right after does not wait on the store again.
        started = time.monotonic()
        detail = client.post('/preview/evaluate', json={**body, 'place_ids': [pid], 'include_gallery': True})
        assert detail.status_code == 200 and time.monotonic() - started < 1
        assert all(p['likes_enabled'] is False for p in detail.json()['places'][pid]['photos'])
        assert detail.json()['places'][pid]['scoring']['evidence_photo_url'] == cover['url']
        # Health stays 200 for the working service and names the degraded part.
        started = time.monotonic()
        health = client.get('/health')
        assert health.status_code == 200 and time.monotonic() - started < 2
        assert health.json()['ok'] is True and health.json()['likes'] == {'configured': True, 'reachable': False}
        # Writes still tell the browser, immediately while the outage is known.
        assert client.post('/preview/photo-likes/session', json={}).status_code == 200
        started = time.monotonic()
        like = client.post('/preview/photo-likes/' + pid, json={'photo_id': cover['photo_id'], 'liked': True})
        assert like.status_code == 503 and '좋아요 저장소' in like.json()['title'] and time.monotonic() - started < 1
        # Events are dropped, not failed; account deletion carries on with a logged hash.
        assert client.post('/preview/events', json={'event': 'place_view', 'route': '/place/x', 'session_id': 'abcdefgh1234'}).status_code == 503
        assert likes.remove_voter('account:gone') is False
    warnings = [r for r in caplog.records if 'Photo likes store unavailable' in r.getMessage()]
    assert len([r for r in warnings if r.levelno == logging.WARNING]) == 1    # once per minute, not per request
    assert any(r.levelno == logging.ERROR and likes.voter_hash('account:gone') in r.getMessage() for r in warnings)
    assert 'u:p@' not in caplog.text                                           # never the DSN
    assert not any(r.name == 'psycopg.pool' and r.levelno < logging.ERROR for r in caplog.records)   # retries stay quiet


def test_store_recovers_after_the_cooldown(monkeypatch):
    monkeypatch.setitem(likes._state, 'outage_until', time.monotonic() + 0.2)
    monkeypatch.setenv('PHOTO_LIKES_DATABASE_URL', 'postgresql://unused@localhost:1/unused')
    assert likes.available() is False and likes.read(['p']) == ({}, [], False) and likes.evidence_for({'p': {}}) == {}
    with pytest.raises(PoolTimeout):
        with likes.connection():
            pass
    time.sleep(0.25)
    assert likes.available() is True


def test_store_errors_are_mapped_to_503_only_on_like_routes():
    def request(path):
        return Request({'type': 'http', 'method': 'POST', 'path': path, 'raw_path': path.encode(), 'query_string': b'',
                        'headers': [], 'scheme': 'http', 'server': ('testserver', 80), 'client': ('testclient', 1)})
    response = asyncio.run(likes_database_error(request('/preview/photo-likes/some-place'), PoolTimeout('x')))
    assert response.status_code == 503
    with pytest.raises(PoolTimeout):
        asyncio.run(likes_database_error(request('/preview/evaluate'), PoolTimeout('x')))


def test_events_are_validated_and_dropped_without_a_store(monkeypatch):
    monkeypatch.delenv('PHOTO_LIKES_DATABASE_URL', raising=False)
    ok = {'event': 'landing_view', 'route': '/home', 'session_id': 'abcdefgh1234', 'utm': {'utm_source': 'kakao'}, 'props': {'ok': True}}
    with TestClient(app) as client:
        assert client.post('/preview/events', json=ok).status_code == 503
        # ErrorBoundary report: allowlisted name, bounded message, no stack or URL query.
        crash = {**ok, 'event': 'client_error', 'route': '/place/x', 'props': {'name': 'TypeError', 'message': 'x' * 200, 'platform': 'web'}}
        assert client.post('/preview/events', json=crash).status_code == 503
        for bad in [{**ok, 'event': 'pageview'}, {**ok, 'route': '/home?birth=1993'}, {**ok, 'session_id': 'short'},
                    {**ok, 'utm': {'gclid': 'x'}}, {**ok, 'props': {str(i): i for i in range(21)}},
                    {**ok, 'props': {'note': 'x' * 201}}, {**ok, 'email': 'a@b.c'}]:
            assert client.post('/preview/events', json=bad).status_code == 422, bad
        monkeypatch.setattr(analytics_routes, 'limits', [('/', SlidingWindow(1))])
        assert client.post('/preview/events', json=ok).status_code == 503
        assert client.post('/preview/events', json=ok).status_code == 429
    oversized = fake_request('/preview/events', headers={'content-length': '5000'}, method='POST')
    with pytest.raises(HTTPException) as too_large:
        analytics_routes.record(oversized, None)
    assert too_large.value.status_code == 413
    monkeypatch.setattr(analytics_routes, 'limits', [('/', SlidingWindow(0))])
    api = create_app(Settings(jwt_secret='test-secret-with-at-least-32-characters'), verifiers={})
    with TestClient(api) as client:
        assert client.post('/v1/events', json=ok).status_code == 503          # anonymous, no account id stored
        invalid = client.post('/v1/events', json={**ok, 'event': 'pageview'})
        assert invalid.status_code == 422 and invalid.headers['content-type'].startswith('application/problem+json')


def test_cache_control_distinguishes_bundles_api_and_html(tmp_path):
    assert observability.cache_control('/_expo/static/js/web/entry-abc.js') == observability.IMMUTABLE
    assert observability.cache_control('/assets/fonts/a.ttf') == observability.IMMUTABLE
    assert observability.cache_control('/preview/evaluate') == observability.cache_control('/v1/me') == 'no-store'
    assert observability.cache_control('/health') == 'no-store' and observability.cache_control('/place/x', 'text/html; charset=utf-8') == 'no-store'
    assert observability.cache_control('/robots.txt') == observability.PUBLIC_HOUR and observability.cache_control('/media/a.jpg') is None
    for name in ('_expo/static/js/web/entry-abc.js', 'assets/a.png', 'index.html'):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text('x' * 10)
    site = FastAPI()
    site.add_middleware(observability.ResponseHeaders)
    site.frontend('/', directory=tmp_path, fallback=None)
    with TestClient(site) as client:
        bundle = client.get('/_expo/static/js/web/entry-abc.js')
        assert bundle.headers['cache-control'] == observability.IMMUTABLE and bundle.headers['x-content-type-options'] == 'nosniff'
        assert client.get('/assets/a.png').headers['cache-control'] == observability.IMMUTABLE
        assert client.get('/').headers['cache-control'] == 'no-store'
    with TestClient(app) as client:
        assert client.post('/preview/profile', json={}).headers['cache-control'] == 'no-store'
        assert client.get('/health').headers['referrer-policy'] == 'no-referrer'


def test_gzip_skips_small_bodies_and_auth_token_responses():
    api = create_app(Settings(jwt_secret='test-secret-with-at-least-32-characters'), verifiers={})

    @api.get('/v1/auth/big-probe')
    def auth_probe():
        return {'token': 'x' * 5000}

    @api.get('/v1/big-probe')
    def probe():
        return {'data': 'x' * 5000}

    @api.get('/v1/small-probe')
    def small():
        return {'ok': True}
    with TestClient(api) as client:
        gz = {'Accept-Encoding': 'gzip'}
        assert client.get('/v1/big-probe', headers=gz).headers.get('content-encoding') == 'gzip'
        assert 'content-encoding' not in client.get('/v1/small-probe', headers=gz).headers
        assert 'content-encoding' not in client.get('/v1/auth/big-probe', headers=gz).headers
        small_response = client.get('/v1/small-probe', headers=gz)
        assert small_response.headers['cache-control'] == 'no-store' and small_response.headers['x-content-type-options'] == 'nosniff'


def fake_request(path='/v1/x', peer='10.0.0.9', headers=None, scheme='http', method='GET'):
    return SimpleNamespace(method=method, url=SimpleNamespace(path=path, scheme=scheme),
                           client=SimpleNamespace(host=peer), headers=headers or {})


def test_forwarded_headers_count_only_from_trusted_proxies(monkeypatch):
    monkeypatch.delenv('VERCEL', raising=False)
    monkeypatch.delenv('FORWARDED_ALLOW_IPS', raising=False)
    spoofed = {'x-forwarded-for': '1.2.3.4, 203.0.113.5, 10.0.0.9', 'x-real-ip': '1.2.3.4', 'x-forwarded-proto': 'https'}
    assert rate_limit.client_ip(fake_request(headers=spoofed)) == '10.0.0.9'
    assert rate_limit.forwarded_scheme(fake_request(headers=spoofed)) == 'http'
    monkeypatch.setenv('FORWARDED_ALLOW_IPS', '10.0.0.9')
    assert rate_limit.client_ip(fake_request(headers=spoofed)) == '203.0.113.5'     # right-most untrusted hop
    assert rate_limit.forwarded_scheme(fake_request(headers=spoofed)) == 'https'
    assert rate_limit.client_ip(fake_request(peer='10.0.0.8', headers=spoofed)) == '10.0.0.8'
    assert rate_limit.client_ip(fake_request(headers={})) == '10.0.0.9'
    monkeypatch.delenv('FORWARDED_ALLOW_IPS')
    monkeypatch.setenv('VERCEL', '1')
    assert rate_limit.client_ip(fake_request(peer='127.0.0.1', headers=spoofed)) == '1.2.3.4'   # Vercel sets x-real-ip itself
    assert rate_limit.client_ip(fake_request(peer='127.0.0.1', headers={'x-forwarded-for': 'a, b'})) == 'b'


def test_authenticated_traffic_keeps_a_loose_per_address_cap(monkeypatch):
    monkeypatch.delenv('VERCEL', raising=False)
    monkeypatch.setenv('RATE_LIMIT_IP_FACTOR', '2')
    rules = [('/v1/', SlidingWindow(2))]
    request = fake_request('/v1/me')
    assert [rate_limit.retry_after(request, rules, user_id=f'u{i}') for i in range(4)] == [None] * 4
    assert rate_limit.retry_after(request, rules, user_id='u4') == 60          # 4 accounts x 2 = address cap
    assert rate_limit.retry_after(fake_request('/v1/me', peer='10.0.0.2'), rules, user_id='u4') is None
    assert rate_limit.retry_after(request, rules) is None                        # anonymous bucket is separate
    monkeypatch.setenv('RATE_LIMIT_IP_FACTOR', '0')
    assert rate_limit.retry_after(request, [('/v1/', SlidingWindow(2))], user_id='u9') is None


def test_json_logs_and_sentry_never_carry_bodies_cookies_or_addresses(monkeypatch):
    record = logging.LogRecord('photospot.http', logging.INFO, __file__, 1, 'request', None, None)
    record.http = {'path': '/preview/evaluate', 'status': 200, 'ms': 12}
    entry = json.loads(observability.JsonFormatter().format(record))
    assert entry['level'] == 'INFO' and entry['path'] == '/preview/evaluate' and entry['status'] == 200 and entry['ts'].endswith('Z')
    monkeypatch.delenv('SENTRY_DSN', raising=False)
    assert observability.init_sentry('api') is False
    import sentry_sdk
    captured = {}
    monkeypatch.setattr(sentry_sdk, 'init', lambda **kwargs: captured.update(kwargs))
    monkeypatch.setenv('SENTRY_DSN', 'https://public@sentry.example/1')
    monkeypatch.setenv('VERCEL_ENV', 'production')
    assert observability.init_sentry('personal-preview') is True
    assert captured['send_default_pii'] is False and captured['max_request_body_size'] == 'never'
    assert captured['environment'] == 'production' and captured['traces_sample_rate'] == 0
    assert {type(i).__name__ for i in captured['integrations']} == {'StarletteIntegration', 'FastApiIntegration'}
    # The SDK attaches the query string to every event regardless of send_default_pii: before_send drops it (lat/lng).
    event = captured['before_send']({'request': {'method': 'GET', 'url': 'https://photospot.litaandd.com/v1/recommendations?lat=37.58&lng=126.98',
                                                 'query_string': 'lat=37.58&lng=126.98', 'headers': {'Host': 'photospot.litaandd.com'}}}, {})
    assert event['request'] == {'method': 'GET', 'url': 'https://photospot.litaandd.com/v1/recommendations', 'headers': {'Host': 'photospot.litaandd.com'}}
    assert captured['before_send_transaction'] is captured['before_send']
    assert observability.scrub_request({'message': 'no request'}, None) == {'message': 'no request'}
    assert all(h.formatter.__class__ is observability.JsonFormatter for h in logging.getLogger().handlers if getattr(h, 'photospot_json', False))


def test_seo_routes_list_public_pages_and_photographed_places(fixture_catalog, monkeypatch):
    from deploy.vercel.frontend import register_seo_routes, places_with_photos
    from api.catalog_media import photo_counts_for
    from pipeline import place_catalog as catalog
    monkeypatch.setenv('PUBLIC_BASE_URL', 'https://example.test/')
    site = FastAPI()
    register_seo_routes(site)
    with catalog.connect() as conn:
        ids = [r[0] for r in conn.execute('SELECT id FROM places WHERE active=1')]
    without = next(pid for pid in ids if not photo_counts_for([pid]).get(pid))
    with TestClient(site) as client:
        robots = client.get('/robots.txt').text
        assert robots.splitlines() == ['User-agent: *', 'Disallow: /admin', 'Disallow: /accounts', 'Disallow: /oauth/',
                                       'Sitemap: https://example.test/sitemap.xml']
        sitemap = client.get('/sitemap.xml')
        assert sitemap.status_code == 200 and client.head('/sitemap.xml').status_code == 200
        assert '<loc>https://example.test/</loc>' in sitemap.text and '<loc>https://example.test/home</loc>' in sitemap.text
        listed = places_with_photos()
        assert listed and all(f'<loc>https://example.test/place/{pid}</loc>' in sitemap.text for pid in listed)
        assert without not in sitemap.text and '/admin' not in sitemap.text


def test_vercel_config_pins_seoul_redirects_the_old_host_and_caches_bundles():
    config = json.loads((ROOT / 'vercel.json').read_text(encoding='utf-8'))
    assert config['regions'] == ['icn1']
    redirect = config['redirects'][0]
    assert redirect['has'] == [{'type': 'host', 'value': 'photospot-nu.vercel.app'}]
    assert redirect['destination'] == 'https://photospot.litaandd.com/$1' and redirect['permanent'] is True
    rules = {rule['source']: {h['key']: h['value'] for h in rule['headers']} for rule in config['headers']}
    assert rules['/(.*)']['Strict-Transport-Security'] == 'max-age=63072000; includeSubDomains'
    assert 'Cache-Control' not in rules['/(.*)']
    for source in ('/_expo/static/(.*)', '/assets/(.*)'):
        assert rules[source] == {'Cache-Control': 'public, max-age=31536000, immutable'}
    assert config['functions']['deploy/vercel/index.py']['maxDuration'] == 60
