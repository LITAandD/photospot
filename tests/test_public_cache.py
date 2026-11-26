"""Public browse responses are shared briefly; personal, failing and cookie-setting replies never are."""
from datetime import date
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, Response
from fastapi.testclient import TestClient

from api import catalog_recommendations as rec, observability, photo_likes, preview, public_cache
from api.preview import PreviewIn
from pipeline import place_catalog as catalog

D = date(2026, 11, 27)


def test_middleware_keeps_shared_policy_only_for_successful_cookieless_reads():
    site = FastAPI()
    site.add_middleware(observability.ResponseHeaders)

    @site.api_route('/preview/ok', methods=['GET', 'HEAD', 'POST'])
    def ok():
        return Response('{}', media_type='application/json', headers={'Cache-Control': observability.SHARED_BROWSE})

    @site.get('/preview/missing')
    def missing():
        return Response('{}', status_code=404, media_type='application/json', headers={'Cache-Control': observability.SHARED_BROWSE})

    @site.get('/preview/cookie')
    def cookie():
        response = Response('{}', media_type='application/json', headers={'Cache-Control': observability.SHARED_BROWSE})
        response.set_cookie('voter', 'x')
        return response

    @site.get('/media/thing')
    def other():
        return Response('x', status_code=500, headers={'Cache-Control': observability.SHARED_SHELL})

    with TestClient(site) as client:
        assert client.get('/preview/ok').headers['cache-control'] == observability.SHARED_BROWSE
        assert client.head('/preview/ok').headers['cache-control'] == observability.SHARED_BROWSE
        assert client.post('/preview/ok').headers['cache-control'] == 'no-store'
        assert client.get('/preview/missing').headers['cache-control'] == 'no-store'
        assert client.get('/preview/cookie').headers['cache-control'] == 'no-store'
        # A path with no default policy still never keeps a shared header on failure.
        assert client.get('/media/thing').headers['cache-control'] == 'no-store'
        # Routes that do not opt in keep their previous policy.
        assert observability.cache_control('/preview/evaluate') == 'no-store'


def test_spa_shells_and_public_pages_are_cdn_shareable_except_sign_in(tmp_path):
    from deploy.vercel.frontend import PRIVATE_SHELLS, SPA_ROUTES, register_spa_routes
    entry = tmp_path / 'index.html'
    entry.write_text('<html><head><title>포토스팟</title><link rel="canonical" href="/"></head></html>', encoding='utf-8')
    site = FastAPI()
    site.add_middleware(observability.ResponseHeaders)
    register_spa_routes(site, entry)
    with TestClient(site) as client:
        for path in SPA_ROUTES:
            url = path.replace('{rec_id}', 'r1').replace('{place_id}', 'p1')
            expected = 'no-store' if path in PRIVATE_SHELLS else observability.SHARED_SHELL
            assert client.get(url).headers['cache-control'] == expected, path
        assert client.get('/oauth/naver?code=one-time&state=s').headers['cache-control'] == 'no-store'
        assert client.get('/browse?city=seoul&date=2026-11-27').headers['cache-control'] == observability.SHARED_BROWSE
        shot = client.get('/today-shot?city=seoul&date=2026-11-27')
        assert shot.headers['cache-control'] == observability.SHARED_BROWSE and shot.headers['x-robots-tag'] == 'noindex, nofollow'
        missing = client.get(f'/browse/{uuid4()}?city=seoul')
        assert missing.status_code == 404 and missing.headers['cache-control'] == 'no-store'


def test_browse_pages_preload_the_exact_api_request_the_app_sends(tmp_path, monkeypatch):
    from deploy.vercel import frontend
    monkeypatch.setattr('pipeline.catalog_visitors.today', lambda: date(2026, 11, 26))
    entry = tmp_path / 'index.html'
    entry.write_text('<html><head><title>포토스팟</title><link rel="canonical" href="/"></head></html>', encoding='utf-8')
    site = FastAPI()
    frontend.register_spa_routes(site, entry)
    preload = '<link rel="preload" as="fetch" href="/preview/browse?city={}&amp;visit_date={}" crossorigin="anonymous">'
    with TestClient(site) as client:
        assert preload.format('seoul', '2026-11-28') in client.get('/browse?city=seoul&date=2026-11-28').text
        # Same fallback as browseDate(): malformed or impossible dates become today in KST.
        for bad in ('2026-02-30', '2026-1-5', 'x'):
            assert preload.format('jeju', '2026-11-26') in client.get(f'/browse?city=jeju&date={bad}').text
        assert 'rel="preload"' not in client.get('/browse').text
        assert 'rel="preload"' not in client.get('/home').text
    monkeypatch.setenv('PLACE_CATALOG_DB', str(tmp_path / 'detail.sqlite3'))
    catalog.import_response('seoul', {'elements': [
        {'type': 'node', 'id': 1, 'lat': 37.5806, 'lon': 126.977, 'tags': {'name': 'Museum 1', 'tourism': 'museum'}}]})
    pid = catalog.search(37.5796, 126.977, 5000)[0]['id']
    with TestClient(site) as client:
        page = client.get(f'/browse/{pid}?city=seoul&date=2026-11-28')
        assert page.status_code == 200
        assert f'<link rel="preload" as="fetch" href="/preview/browse/{pid}?city=seoul&amp;visit_date=2026-11-28" crossorigin="anonymous">' in page.text
        assert 'rel="preload"' not in client.get(f'/browse/{uuid4()}?city=seoul').text


@pytest.fixture
def reuse(monkeypatch):
    clock = {'now': 1000.0}
    monkeypatch.setenv('PUBLIC_BROWSE_CACHE_S', '300')
    monkeypatch.setattr(public_cache, '_cache', public_cache.TTLCache(clock=lambda: clock['now']))
    calls = []

    def fake_list(city, visit_date):
        from api.public_place_info import ORIGINS
        calls.append((city, visit_date))
        return {'items': [], 'browse_origin': ORIGINS[city]}
    monkeypatch.setattr(preview, 'public_list', fake_list)
    return clock, calls


def test_browse_answer_is_reused_within_window_and_per_city_date(reuse):
    clock, calls = reuse
    with TestClient(preview.app) as client:
        first = client.get(f'/preview/browse?city=seoul&visit_date={D}')
        again = client.get(f'/preview/browse?city=seoul&visit_date={D}')
        assert first.json() == again.json() and len(calls) == 1
        assert again.headers['cache-control'] == observability.SHARED_BROWSE_DATA and 'set-cookie' not in again.headers
        client.get(f'/preview/browse?city=busan&visit_date={D}')
        client.get('/preview/browse?city=seoul&visit_date=2026-11-28')
        assert len(calls) == 3
        clock['now'] += 301
        client.get(f'/preview/browse?city=seoul&visit_date={D}')
        assert len(calls) == 4
        assert client.get('/preview/browse?city=nowhere&visit_date=2026-11-27').headers['cache-control'] == 'no-store'


def test_degraded_likes_answer_is_neither_kept_nor_shared(reuse, monkeypatch):
    _, calls = reuse
    monkeypatch.setattr(photo_likes, 'configured', lambda: True)
    monkeypatch.setattr(photo_likes, 'available', lambda: False)
    with TestClient(preview.app) as client:
        for _ in range(2):
            response = client.get(f'/preview/browse?city=seoul&visit_date={D}')
            assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert len(calls) == 2


def test_reuse_is_off_outside_vercel_unless_configured(monkeypatch):
    monkeypatch.delenv('PUBLIC_BROWSE_CACHE_S', raising=False)
    monkeypatch.delenv('VERCEL', raising=False)
    assert public_cache.ttl_seconds() == 0
    monkeypatch.setenv('VERCEL', '1')
    assert public_cache.ttl_seconds() == public_cache.DEFAULT_SECONDS
    monkeypatch.setenv('PUBLIC_BROWSE_CACHE_S', 'oops')
    assert public_cache.ttl_seconds() == 0


def test_missing_detail_is_not_kept(monkeypatch):
    monkeypatch.setenv('PUBLIC_BROWSE_CACHE_S', '300')
    monkeypatch.setattr(public_cache, '_cache', public_cache.TTLCache())
    calls = []

    def missing(place_id, city, visit_date):
        calls.append(place_id)
        raise HTTPException(404, '선택한 도시의 둘러보기 범위에서 이 장소를 찾지 못했어요.')
    monkeypatch.setattr(preview, 'public_detail', missing)
    pid = uuid4()
    with TestClient(preview.app) as client:
        for _ in range(2):
            response = client.get(f'/preview/browse/{pid}?city=seoul&visit_date={D}')
            assert response.status_code == 404 and response.headers['cache-control'] == 'no-store'
    assert len(calls) == 2


def test_public_browse_explains_only_returned_places(tmp_path, monkeypatch):
    monkeypatch.setenv('PLACE_CATALOG_DB', str(tmp_path / 'browse.sqlite3'))
    catalog.import_response('seoul', {'elements': [
        {'type': 'node', 'id': n, 'lat': 37.5796 + n * .001, 'lon': 126.977,
         'tags': {'name': f'Museum {n}', 'tourism': 'museum'}} for n in range(1, 16)]})
    explained = []
    original = rec.explanation

    def counting(*args, **kwargs):
        explained.append(args[2]['id'])
        return original(*args, **kwargs)
    monkeypatch.setattr(rec, 'explanation', counting)
    body = PreviewIn(visit_date=D, limit=3)
    public = rec.recommend(body, {}, public_browse=True)['recommendations'].items
    assert len(public) == 3 and sorted(explained) == sorted(item.place_id for item in public)
    explained.clear()
    personal = rec.recommend(body, {})['recommendations'].items
    assert len(personal) == 3 and len(explained) == len(catalog.search(37.5796, 126.977, 5000))
