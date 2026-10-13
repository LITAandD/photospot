"""Shared votes, exact-image scoring and browser authorization contracts."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest
from fastapi.testclient import TestClient

from api import photo_likes as likes
from api.photo_like_routes import COOKIE
from api.preview import app
from pipeline import catalog_photos, catalog_visuals, place_catalog
from pipeline.photo_identity import photo_id
from tests.test_catalog_photos import image_page


@pytest.fixture
def shared_store(monkeypatch):
    dsn = os.environ.get('PHOTO_LIKES_TEST_DATABASE_URL') or os.environ.get('DATABASE_URL')
    if not dsn:
        pytest.skip('PostgreSQL integration database required')
    schema = 'likes_test_' + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    isolated = make_conninfo(dsn, options='-c search_path=' + schema)
    monkeypatch.setenv('PHOTO_LIKES_DATABASE_URL', isolated)
    monkeypatch.setenv('PHOTO_LIKES_COOKIE_SECRET', 'test-only-cookie-secret-' * 3)
    likes.migrate()
    yield isolated
    likes.pool(isolated).close()
    likes.pool.cache_clear()
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


@pytest.fixture
def venue(tmp_path, monkeypatch):
    path = tmp_path / 'catalog.sqlite3'
    monkeypatch.setenv('PLACE_CATALOG_DB', str(path))
    place_catalog.import_response('seoul', {'elements': [
        {'type': 'node', 'id': 1, 'lat': 37.5796, 'lon': 126.977,
         'tags': {'name': 'A', 'amenity': 'cafe'}}]}, path)
    place = place_catalog.search(37.5796, 126.977, 1000, path=path)[0]
    photos = []
    for i, name in enumerate(('Interior', 'Garden')):
        page = image_page('File:' + name + '.jpg')
        for field in ('url', 'thumburl', 'descriptionurl'):
            page['imageinfo'][0][field] = page['imageinfo'][0][field].replace('Place.jpg', name + '.jpg')
        photos.append({**catalog_photos.reusable_image(page), 'place_id': place['id'],
                       'match_method': 'reviewed:branch', 'match_ref': 'test', 'priority': i})
    catalog_photos.store_photos(photos, path)
    catalog_visuals.store(place['id'], photos[0], {'color_temp': 'warm'}, 'fixture', path)
    monkeypatch.setattr(likes, 'analyze_photo', lambda pid, p: {
        'photo_url': p['url'], 'source_url': p['source_url'],
        'attributes': {'color_temp': 'cool'}, 'method': 'fixture:photo-specific'})
    return place['id'], photos


def evaluation(client, pid):
    response = client.post('/preview/evaluate', json={'profile': {'pc_season': 'spring_warm'},
        'visit_date': '2026-10-13', 'place_ids': [pid], 'include_gallery': True})
    assert response.status_code == 200, response.text
    body = response.json()
    return body['places'][pid], next(i for i in body['recommendations']['items'] if i['place_id'] == pid)


def test_two_browsers_change_shared_cover_exact_score_and_reversible_total(shared_store, venue):
    pid, photos = venue
    key = photo_id(photos[1])
    with TestClient(app) as first, TestClient(app) as second:
        for client in (first, second):
            session = client.post('/preview/photo-likes/session', json={})
            assert session.status_code == 200 and 'HttpOnly' in session.headers['set-cookie']
        initial, _ = evaluation(first, pid)
        assert initial['photos'][0]['url'] == photos[0]['url'] and initial['fit_score'] == 28
        for _ in range(2):
            liked = first.post('/preview/photo-likes/' + pid, json={'photo_id': key, 'liked': True})
            assert liked.json()['like_count'] == 1
        detail, card = evaluation(first, pid)
        assert detail['photos'][0]['photo_id'] == key and detail['photos'][0]['liked']
        assert card['cover_photo'] == detail['photos'][0]
        assert detail['fit_score'] == card['fit_score'] == 0
        assert detail['scoring']['evidence_photo_url'] == photos[1]['url']
        assert detail['scoring']['evidence_url'] == photos[1]['source_url']
        assert not evaluation(second, pid)[0]['photos'][0]['liked']
        assert second.post('/preview/photo-likes/' + pid, json={'photo_id': key, 'liked': True}).json()['like_count'] == 2
        assert first.post('/preview/photo-likes/' + pid, json={'photo_id': key, 'liked': False}).json()['like_count'] == 1
        # A new application instance reads persisted totals; no process cache is authoritative.
        with TestClient(app) as fresh:
            assert evaluation(fresh, pid)[0]['photos'][0]['like_count'] == 1
        assert second.post('/preview/photo-likes/' + pid, json={'photo_id': key, 'liked': False}).json()['like_count'] == 0
        after, _ = evaluation(first, pid)
        assert after['photos'][0]['url'] == photos[0]['url'] and after['fit_score'] == 28


def test_concurrent_retries_do_not_create_duplicate_votes(shared_store, venue):
    pid, photos = venue
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda _: likes.set_like(pid, photos[0], 'same-browser', True), range(9)))
    assert all(r['like_count'] == 1 for r in results)
    totals, enabled = likes.snapshot([pid], 'same-browser')
    assert enabled and totals[pid, photo_id(photos[0])] == {'liked': True, 'like_count': 1}
    assert likes.set_like(pid, photos[0], 'same-browser', False)['like_count'] == 0
    assert likes.set_like(pid, photos[0], 'same-browser', False)['like_count'] == 0


def test_browser_writes_require_signed_cookie_same_origin_and_current_allowed_photo(shared_store, venue):
    pid, photos = venue
    body = {'photo_id': photo_id(photos[0]), 'liked': True}
    with TestClient(app) as client:
        assert client.post('/preview/photo-likes/' + pid, json=body).status_code == 428
        assert client.post('/preview/photo-likes/session', json={}, headers={'Origin': 'https://evil.example'}).status_code == 403
        assert client.post('/preview/photo-likes/session', content='{}').status_code == 415
        client.cookies.set(COOKIE, 'a' * 64 + '.' + 'b' * 64)
        assert client.post('/preview/photo-likes/' + pid, json=body).status_code == 428
        client.cookies.clear()
        client.post('/preview/photo-likes/session', json={})
        assert client.post('/preview/photo-likes/' + pid, json={**body, 'liked': 'true'}).status_code == 422
        assert client.post('/preview/photo-likes/' + pid, json={**body, 'photo_id': '0' * 64}).status_code == 404
        with place_catalog.connect() as conn:
            conn.execute("UPDATE catalog_photos SET license_url='' WHERE place_id=?", (pid,))
        assert client.post('/preview/photo-likes/' + pid, json=body).status_code == 404


def test_failed_analysis_never_reuses_previous_cover_attributes(shared_store, venue, monkeypatch):
    pid, photos = venue
    def offline(*args):
        raise OSError('offline')
    monkeypatch.setattr(likes, 'analyze_photo', offline)
    with TestClient(app) as client:
        client.post('/preview/photo-likes/session', json={})
        response = client.post('/preview/photo-likes/' + pid, json={'photo_id': photo_id(photos[1]), 'liked': True})
        assert response.status_code == 200
        detail, _ = evaluation(client, pid)
        assert detail['photos'][0]['url'] == photos[1]['url']
        assert detail['fit_score'] is None and detail['scoring']['photo_analysis_pending']
        assert detail['scoring']['evidence_url'] is None


def test_identity_survives_thumbnail_size_change_and_ties_are_stable():
    first = {'url': 'thumb-1', 'original_url': 'original', 'source_url': 'source'}
    second = {'url': 'thumb-2', 'source_url': 'other'}
    assert photo_id(first) == photo_id({**first, 'url': 'different-size'})
    ranked = likes.rank({'p': [first, second]}, {}, True)['p']
    assert [p['url'] for p in ranked] == ['thumb-1', 'thumb-2']
    ranked = likes.rank({'p': [first, second]}, {('p', photo_id(second)): {'like_count': 4, 'liked': True}}, True)['p']
    assert ranked[0]['url'] == 'thumb-2'


def test_schema_contains_no_profile_or_raw_browser_data():
    text = Path(likes.__file__).with_suffix('.sql').read_text(encoding='utf-8')
    assert 'PRIMARY KEY (place_id, photo_id, voter_hash)' in text
    assert not any(field in text for field in ('birth_date', 'client_ip', 'cookie_token'))


def test_color_analysis_needs_no_cluster_model(monkeypatch):
    import sys
    from PIL import Image
    monkeypatch.setitem(sys.modules, 'sklearn', None)
    warm = catalog_visuals.color_attributes(Image.new('RGB', (32, 32), '#dca05a'))
    cool = catalog_visuals.color_attributes(Image.new('RGB', (32, 32), '#7f9cbf'))
    assert warm['color_temp'] == 'warm' and cool['color_temp'] == 'cool'
    assert set(warm) == {'color_temp', 'brightness', 'saturation'}


@pytest.mark.parametrize('url', ['https://localhost/private', 'http://postfiles.pstatic.net/a.jpg',
    'https://postfiles.pstatic.net.evil.example/a.jpg', 'https://user@postfiles.pstatic.net/a.jpg',
    'https://www.visitbusan.net:8080/a.jpg'])
def test_analysis_rejects_untrusted_image_urls_before_network(url):
    with pytest.raises(ValueError, match='Unsupported image host'):
        catalog_visuals.read_photo(url)
