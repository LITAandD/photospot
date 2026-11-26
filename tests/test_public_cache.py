"""Public browse responses are shared briefly; personal, failing and cookie-setting replies never are."""
from datetime import date, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, Response
from fastapi.testclient import TestClient

from api import catalog_recommendations as rec, observability, photo_likes, preview, public_cache
from api.preview import PreviewIn
from pipeline import place_catalog as catalog

D = date(2026, 11, 27)
SHORT = observability.shared(300)


def test_shared_policy_helper_and_middleware_keep_it_only_for_successful_cookieless_reads():
    assert observability.shared(300, max_age=60) == 'public, max-age=60, s-maxage=300'
    assert observability.shared(30, max_age=60) == 'public, max-age=30, s-maxage=30'
    assert observability.shared(0) == observability.shared(-5) == 'no-store'
    site = FastAPI()
    site.add_middleware(observability.ResponseHeaders)

    @site.api_route('/preview/ok', methods=['GET', 'HEAD', 'POST'])
    def ok():
        return Response('{}', media_type='application/json', headers={'Cache-Control': SHORT})

    @site.get('/preview/missing')
    def missing():
        return Response('{}', status_code=404, media_type='application/json', headers={'Cache-Control': SHORT})

    @site.get('/preview/cookie')
    def cookie():
        response = Response('{}', media_type='application/json', headers={'Cache-Control': SHORT})
        response.set_cookie('voter', 'x')
        return response

    @site.get('/media/thing')
    def other():
        return Response('x', status_code=500, headers={'Cache-Control': observability.SHARED_PER_DEPLOY})

    with TestClient(site) as client:
        assert client.get('/preview/ok').headers['cache-control'] == SHORT
        assert client.head('/preview/ok').headers['cache-control'] == SHORT
        assert client.post('/preview/ok').headers['cache-control'] == 'no-store'
        assert client.get('/preview/missing').headers['cache-control'] == 'no-store'
        assert client.get('/preview/cookie').headers['cache-control'] == 'no-store'
        # A path with no default policy still never keeps a shared header on failure.
        assert client.get('/media/thing').headers['cache-control'] == 'no-store'
        # Routes that do not opt in keep their previous policy.
        assert observability.cache_control('/preview/evaluate') == 'no-store'


def test_spa_shells_and_public_pages_are_cdn_shareable_except_sign_in(tmp_path, monkeypatch):
    from deploy.vercel.frontend import PRIVATE_SHELLS, SPA_ROUTES, register_spa_routes
    monkeypatch.setattr(public_cache, 'seconds_until_kst_midnight', lambda now=None: 120)
    entry = tmp_path / 'index.html'
    entry.write_text('<html><head><title>포토스팟</title><link rel="canonical" href="/"></head></html>', encoding='utf-8')
    site = FastAPI()
    site.add_middleware(observability.ResponseHeaders)
    register_spa_routes(site, entry)
    with TestClient(site) as client:
        for path in SPA_ROUTES:
            url = path.replace('{rec_id}', 'r1').replace('{place_id}', 'p1')
            expected = 'no-store' if path in PRIVATE_SHELLS else observability.SHARED_PER_DEPLOY
            assert client.get(url).headers['cache-control'] == expected, path
        assert client.get('/oauth/naver?code=one-time&state=s').headers['cache-control'] == 'no-store'
        # Browse HTML depends only on the URL and the deployed catalog.
        assert client.get('/browse?city=seoul').headers['cache-control'] == observability.SHARED_PER_DEPLOY
        # The shot page title follows today's verified cuts, so it is shared only until KST midnight.
        shot = client.get('/today-shot?city=seoul&date=2026-11-27')
        assert shot.headers['cache-control'] == 'public, max-age=0, s-maxage=120' and shot.headers['x-robots-tag'] == 'noindex, nofollow'
        missing = client.get(f'/browse/{uuid4()}?city=seoul')
        assert missing.status_code == 404 and missing.headers['cache-control'] == 'no-store'


def test_browse_pages_preload_the_exact_dated_api_request_the_app_sends(tmp_path, monkeypatch):
    from deploy.vercel import frontend
    entry = tmp_path / 'index.html'
    entry.write_text('<html><head><title>포토스팟</title><link rel="canonical" href="/"></head></html>', encoding='utf-8')
    site = FastAPI()
    frontend.register_spa_routes(site, entry)
    preload = '<link rel="preload" as="fetch" href="/preview/browse?city={}&amp;visit_date={}" crossorigin="anonymous">'
    with TestClient(site) as client:
        assert preload.format('seoul', '2026-11-28') in client.get('/browse?city=seoul&date=2026-11-28').text
        # Without a usable date the app asks for its own today, so the shared page carries no preload.
        for url in ('/browse?city=jeju', '/browse?city=jeju&date=2026-02-30', '/browse?city=jeju&date=2026-1-5', '/browse', '/home'):
            assert 'rel="preload"' not in client.get(url).text, url
    monkeypatch.setenv('PLACE_CATALOG_DB', str(tmp_path / 'detail.sqlite3'))
    catalog.import_response('seoul', {'elements': [
        {'type': 'node', 'id': 1, 'lat': 37.5806, 'lon': 126.977, 'tags': {'name': 'Museum 1', 'tourism': 'museum'}}]})
    pid = catalog.search(37.5796, 126.977, 5000)[0]['id']
    with TestClient(site) as client:
        page = client.get(f'/browse/{pid}?city=seoul&date=2026-11-28')
        assert page.status_code == 200
        assert f'<link rel="preload" as="fetch" href="/preview/browse/{pid}?city=seoul&amp;visit_date=2026-11-28" crossorigin="anonymous">' in page.text
        assert 'rel="preload"' not in client.get(f'/browse/{pid}?city=seoul').text


@pytest.fixture
def reuse(monkeypatch):
    clock = {'now': 1000.0}
    monkeypatch.setenv('PUBLIC_BROWSE_CACHE_S', '300')
    monkeypatch.setattr(public_cache, '_cache', public_cache.TTLCache(clock=lambda: clock['now']))
    monkeypatch.setattr(public_cache, 'seconds_until_kst_midnight', lambda now=None: 86400)
    calls = []

    def fake_list(city, visit_date):
        from api.public_place_info import ORIGINS
        calls.append((city, visit_date))
        return {'items': [], 'browse_origin': ORIGINS[city]}
    monkeypatch.setattr(preview, 'public_list', fake_list)
    return clock, calls


def test_browse_answer_is_reused_and_every_copy_expires_with_it(reuse, monkeypatch):
    clock, calls = reuse
    url = f'/preview/browse?city=seoul&visit_date={D}'
    with TestClient(preview.app) as client:
        first = client.get(url)
        assert first.headers['cache-control'] == 'public, max-age=60, s-maxage=300' and 'set-cookie' not in first.headers
        clock['now'] += 200
        again = client.get(url)
        assert first.json() == again.json() and len(calls) == 1
        # The CDN and browser get only the 100 seconds the reused answer has left.
        assert again.headers['cache-control'] == 'public, max-age=60, s-maxage=100'
        clock['now'] += 50
        assert client.get(url).headers['cache-control'] == 'public, max-age=50, s-maxage=50'
        client.get(f'/preview/browse?city=busan&visit_date={D}')
        client.get('/preview/browse?city=seoul&visit_date=2026-11-28')
        assert len(calls) == 3
        clock['now'] += 51
        assert client.get(url).headers['cache-control'] == 'public, max-age=60, s-maxage=300' and len(calls) == 4
        # Nothing outlives the KST day it was computed for.
        monkeypatch.setattr(public_cache, 'seconds_until_kst_midnight', lambda now=None: 40)
        assert client.get(url).headers['cache-control'] == 'public, max-age=40, s-maxage=40'
        assert client.get('/preview/browse?city=nowhere&visit_date=2026-11-27').headers['cache-control'] == 'no-store'


def test_zero_disables_reuse_and_sharing(reuse, monkeypatch):
    _, calls = reuse
    monkeypatch.setenv('PUBLIC_BROWSE_CACHE_S', '0')
    with TestClient(preview.app) as client:
        for _ in range(2):
            assert client.get(f'/preview/browse?city=seoul&visit_date={D}').headers['cache-control'] == 'no-store'
    assert len(calls) == 2


@pytest.mark.parametrize('before,after', [(False, False), (False, True), (True, False)],
                         ids=['whole-request', 'cooldown-ends-during-compute', 'fails-during-compute'])
def test_answer_touching_the_likes_outage_is_neither_kept_nor_shared(reuse, monkeypatch, before, after):
    _, calls = reuse
    state = {'available': before}
    monkeypatch.setattr(photo_likes, 'configured', lambda: True)
    monkeypatch.setattr(photo_likes, 'available', lambda: state['available'])
    computed = preview.public_list

    def compute(city, visit_date):
        value = computed(city, visit_date)
        state['available'] = after       # the store recovers or fails while the answer is built
        return value
    monkeypatch.setattr(preview, 'public_list', compute)
    with TestClient(preview.app) as client:
        response = client.get(f'/preview/browse?city=seoul&visit_date={D}')
        assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
        state['available'] = after = True
        healthy = client.get(f'/preview/browse?city=seoul&visit_date={D}')
        assert healthy.headers['cache-control'] == 'public, max-age=60, s-maxage=300'
    assert len(calls) == 2


def test_reuse_window_defaults():
    import os
    saved = {k: os.environ.pop(k, None) for k in ('PUBLIC_BROWSE_CACHE_S', 'VERCEL')}
    try:
        assert public_cache.ttl_seconds() == 0 and public_cache.share_seconds() == public_cache.DEFAULT_SECONDS
        os.environ['VERCEL'] = '1'
        assert public_cache.ttl_seconds() == public_cache.DEFAULT_SECONDS
        os.environ['PUBLIC_BROWSE_CACHE_S'] = 'oops'
        assert public_cache.ttl_seconds() == public_cache.share_seconds() == 0
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
    kst = public_cache.KST
    assert public_cache.seconds_until_kst_midnight(datetime(2026, 11, 27, 23, 59, 30, tzinfo=kst)) == 30
    assert public_cache.seconds_until_kst_midnight(datetime(2026, 11, 27, 0, 0, tzinfo=kst)) == 86400


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
