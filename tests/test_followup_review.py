"""Regression checks for the second review; isolated data, no provider requests."""
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import json
from types import SimpleNamespace
import uuid

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.config import Settings
from api.main import create_app
from api.tokens import issue_access
from api.catalog_recommendations import unique_places
from pipeline import official_place_hours as hours


def hours_fixture(tmp_path, monkeypatch, active, fail=()):
    observed = hours.datetime.now(hours.ZoneInfo('Asia/Seoul')).date()
    records = {str(i): hours.DatedHours(place_id=str(i), store_id=str(i), branch='스타벅스 테스트',
        lat=37.5, lng=127, address='테스트로 10', checked_at=observed - timedelta(days=7),
        date_hours={observed - timedelta(days=7): '08:00–22:00'}) for i in range(1, 5)}
    path = tmp_path / 'hours.json'
    path.write_text(json.dumps([r.model_dump(mode='json') for r in records.values()]), encoding='utf-8')
    @lru_cache
    def entries(): return records
    class Client:
        def __init__(self): self.cache = tmp_path / 'cache'; self.cache.mkdir(exist_ok=True)
        def post(self, action, params):
            if params['in_biz_cd'] in fail: raise OSError('Unavailable')
            if action == 'getStoreView': return {'view': [{'s_biz_code': params['in_biz_cd']}]}
            return {'list': [{'store_time_day': observed.day, 'store_time_week': (observed.weekday()+1) % 7+1,
                              'store_opentime': '0900-2100', 'store_time_hlytag': '1'}]}
    @contextmanager
    def connect(): yield SimpleNamespace(execute=lambda sql: [{'id': i} for i in active])
    monkeypatch.setattr(hours, 'entries', entries)
    monkeypatch.setattr(hours, 'DATA', path)
    monkeypatch.setattr(hours.catalog, 'ROOT', tmp_path)
    monkeypatch.setattr(hours.catalog, 'connect', connect)
    monkeypatch.setattr(hours.official, 'Client', Client)
    monkeypatch.setattr(hours.official, 'match_branches', lambda *args: {i: {'s_biz_code': i} for i in active})
    monkeypatch.setattr(hours.official, 'entry_for', lambda row: {k: v for k, v in records[row['s_biz_code']].model_dump().items()
                                                              if k not in {'place_id', 'checked_at', 'date_hours'}})
    monkeypatch.setattr(hours.official, 'valid_branch', lambda *args: True)
    return path, observed


@pytest.mark.parametrize('active', [[], ['1'], ['1', '2']])
def test_incomplete_catalog_cannot_erase_hours(tmp_path, monkeypatch, active):
    path, _ = hours_fixture(tmp_path, monkeypatch, active)
    before = path.read_bytes()
    with pytest.raises(ValueError): hours.run()
    assert path.read_bytes() == before
    assert not path.with_suffix('.tmp').exists()


def test_partial_refresh_preserves_failure_and_publishes_verified_success(tmp_path, monkeypatch):
    path, observed = hours_fixture(tmp_path, monkeypatch, ['1', '2', '3'], fail=['2'])
    report = hours.run()
    rows = {r['place_id']: r for r in json.loads(path.read_text())}
    assert report['status'] == 'partial' and report['updated'] == 2 and report['retired'] == ['4']
    assert rows['1']['checked_at'] == observed.isoformat()
    assert rows['2']['checked_at'] == (observed - timedelta(days=7)).isoformat()
    assert rows['2']['date_hours'] == {(observed - timedelta(days=7)).isoformat(): '08:00–22:00'}


def test_all_failed_refresh_is_not_reported_as_success(tmp_path, monkeypatch):
    path, _ = hours_fixture(tmp_path, monkeypatch, ['1', '2', '3', '4'], fail=['1', '2', '3', '4'])
    before = json.loads(path.read_text())
    assert hours.run()['status'] == 'failed'
    assert json.loads(path.read_text()) == before


def test_limited_refresh_reports_unattempted_branches_as_partial(tmp_path, monkeypatch):
    path, observed = hours_fixture(tmp_path, monkeypatch, ['1', '2', '3', '4'])
    report = hours.run(limit=1)
    assert report['status'] == 'partial' and report['updated'] == report['attempted'] == 1
    assert report['candidates'] == 4 and report['unattempted'] == 3 and not report['failures']
    rows = {r['place_id']: r for r in json.loads(path.read_text())}
    assert rows['2']['checked_at'] == (observed - timedelta(days=7)).isoformat()


def test_shared_ip_has_separate_verified_users_but_forged_and_expired_tokens_do_not():
    settings = Settings(rate_limit_api_per_min=2, rate_limit_auth_per_min=60, jwt_secret='test-secret-with-at-least-32-characters')
    app = create_app(settings)
    from api.db import get_conn
    app.dependency_overrides[get_conn] = lambda: SimpleNamespace(cursor=lambda: nullcontext(SimpleNamespace(execute=lambda *args: None)))
    # This route deliberately avoids a DB: limiter identity is signature-verified,
    # while the real protected routes still check account status via current_user.
    @app.get('/v1/limit-probe')
    def probe(): return {'ok': True}
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    token_a, _ = issue_access(a, False, settings)
    token_b, _ = issue_access(b, False, settings)
    with TestClient(app) as client:
        for token in [token_a, token_a, token_b, token_b]:
            assert client.get('/v1/limit-probe', headers={'Authorization': 'Bearer ' + token}).status_code == 200
        assert client.get('/v1/limit-probe', headers={'Authorization': 'Bearer ' + token_a}).status_code == 429
        for expired in [False, True]:
            claims = {'sub': str(uuid.uuid4()), 'iat': datetime.now(timezone.utc)-timedelta(hours=2),
                      'exp': datetime.now(timezone.utc)+timedelta(hours=-1 if expired else 1), 'typ': 'access', 'jti': 'test'}
            bad = jwt.encode(claims, settings.jwt_secret if expired else 'forged-secret-at-least-32-characters', algorithm=settings.jwt_algorithm)
            assert client.get('/v1/limit-probe', headers={'Authorization': 'Bearer ' + bad}).status_code == 200
        assert client.get('/v1/limit-probe').status_code == 429
        for _ in range(3): assert client.get('/v1/health').status_code == 200


def test_duplicate_places_keep_best_rank_without_merging_distant_branches():
    def item(pid, lat, category='scenic', name='기차바위'):
        return ({'id': pid, 'name': name, 'category': category, 'lat': lat, 'lng': 127}, [], 0)
    rows = [item('best', 37.58), item('same', 37.5803, 'viewpoint'), item('distant', 37.7),
            item('other', 37.58, name='다른 바위'), item('different-kind', 37.58, 'cafe')]
    assert [p['id'] for p, *_ in unique_places(rows)] == ['best', 'distant', 'other', 'different-kind']


def test_preview_list_is_compact_gzipped_and_detail_gallery_is_explicit(tmp_path, monkeypatch):
    from scripts.load_catalog_fixture import main
    from api.preview import app
    monkeypatch.setenv('PLACE_CATALOG_DB', str(tmp_path / 'catalog.sqlite3'))
    main()
    body = {'visit_date': '2026-10-10'}
    with TestClient(app) as client:
        response = client.post('/preview/evaluate', json=body, headers={'Accept-Encoding': 'gzip'})
        assert response.status_code == 200 and response.headers['content-encoding'] == 'gzip'
        assert response.json()['places'] == {}
        cover = next(i for i in response.json()['recommendations']['items'] if i['cover_photo'])
        pid = cover['place_id']
        summary = client.post('/preview/evaluate', json={**body, 'place_ids': [pid]}).json()['places'][pid]
        assert len(summary['photos']) == 1
        detail = client.post('/preview/evaluate', json={**body, 'place_ids': [pid], 'include_gallery': True}).json()['places']
        assert set(detail) == {pid} and len(detail[pid]['photos']) == 3
        assert detail[pid]['photos'][0] == cover['cover_photo']
        bad = client.post('/preview/evaluate', json={**body, 'include_gallery': True})
        assert bad.status_code == 422 and '입력값' in bad.json()['detail']
        assert 'Value error' not in bad.text


def test_unknown_frontend_route_is_korean_http_404(tmp_path):
    from pathlib import Path
    from deploy.vercel.frontend import register_spa_routes, SPA_ROUTES
    (tmp_path / 'index.html').write_text('valid SPA entry')
    (tmp_path / '404.html').write_bytes(Path('deploy/vercel/404.html').read_bytes())
    app = FastAPI()
    register_spa_routes(app, tmp_path / 'index.html')
    app.frontend('/', directory=tmp_path, fallback='404.html')
    with TestClient(app) as client:
        assert client.get('/').status_code == 200
        for route in SPA_ROUTES:
            url = route.replace('{place_id}', 'test-place').replace('{rec_id}', '123')
            response = client.get(url + '?date=2026-10-12')
            assert response.status_code == 200 and response.text == 'valid SPA entry', url
            assert client.head(url).status_code == 200
        response = client.get('/missing-route')
        assert response.status_code == 404 and '페이지를 찾을 수 없어요' in response.text
        assert 'Sitemap' not in response.text and '/admin' not in response.text
