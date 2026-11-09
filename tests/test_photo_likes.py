"""Shared votes, exact-image scoring and browser authorization contracts."""
from concurrent.futures import ThreadPoolExecutor
import gc
import os
from pathlib import Path
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

from api import photo_likes as likes
from api import photo_like_routes as routes
from api.photo_like_routes import COOKIE, LikeIn, change_like
from api.preview import app
from api.rate_limit import SlidingWindow
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
    # Single-browser contracts below; the production vote threshold has its own tests.
    monkeypatch.setenv('PHOTO_LIKES_MIN_VOTES', '1')
    monkeypatch.setenv('PHOTO_LIKES_MIN_MARGIN', '1')
    monkeypatch.setitem(likes._state, 'outage_until', 0.0)
    # Per-process address limits would otherwise accumulate across this module's tests.
    monkeypatch.setattr(routes, 'limits', [('/preview/photo-likes', SlidingWindow(0))])
    monkeypatch.setattr(routes, 'daily_limits', [('/preview/photo-likes/session', SlidingWindow(0)), ('/preview/photo-likes/', SlidingWindow(0))])
    likes.migrate()
    yield isolated
    likes.pool(isolated).close()
    likes.pool.cache_clear()
    gc.collect()
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
        curated_fit = initial['fit_score']
        assert initial['photos'][0]['url'] == photos[0]['url'] and curated_fit > 0
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
        assert after['photos'][0]['url'] == photos[0]['url'] and after['fit_score'] == curated_fit
        health = first.get('/health').json()
        assert health['likes'] == {'configured': True, 'reachable': True}


def test_few_anonymous_votes_show_totals_but_keep_the_curated_cover(shared_store, venue, monkeypatch):
    monkeypatch.delenv('PHOTO_LIKES_MIN_VOTES')
    monkeypatch.delenv('PHOTO_LIKES_MIN_MARGIN')
    pid, photos = venue
    key = photo_id(photos[1])
    browsers = [TestClient(app) for _ in range(5)]
    for client in browsers:
        assert client.post('/preview/photo-likes/session', json={}).status_code == 200
    for n, client in enumerate(browsers[:4], start=1):
        assert client.post('/preview/photo-likes/' + pid, json={'photo_id': key, 'liked': True}).json()['like_count'] == n
    detail, card = evaluation(browsers[0], pid)
    # Totals are visible, yet four cleared-cookie votes do not re-pick everyone's cover or evidence.
    assert [p['like_count'] for p in detail['photos']] == [0, 4] and detail['photos'][0]['url'] == photos[0]['url']
    assert card['scoring']['photo_selection'] == 'curated' and detail['scoring']['evidence_photo_url'] == photos[0]['url']
    assert browsers[4].post('/preview/photo-likes/' + pid, json={'photo_id': key, 'liked': True}).json()['like_count'] == 5
    detail, card = evaluation(browsers[0], pid)
    assert detail['photos'][0]['photo_id'] == key and card['scoring']['photo_selection'] == 'likes'
    assert detail['scoring']['evidence_photo_url'] == photos[1]['url'] and detail['fit_score'] == 0


def test_rank_requires_minimum_votes_and_a_margin_over_the_curated_cover(monkeypatch):
    monkeypatch.delenv('PHOTO_LIKES_MIN_VOTES', raising=False)
    monkeypatch.delenv('PHOTO_LIKES_MIN_MARGIN', raising=False)
    curated = {'url': 'curated', 'source_url': 'c'}
    other = {'url': 'other', 'source_url': 'o'}
    third = {'url': 'third', 'source_url': 't'}
    def order(curated_votes, other_votes, third_votes=0):
        votes = {('p', photo_id(curated)): {'like_count': curated_votes, 'liked': False},
                 ('p', photo_id(other)): {'like_count': other_votes, 'liked': False},
                 ('p', photo_id(third)): {'like_count': third_votes, 'liked': False}}
        return [p['url'] for p in likes.rank({'p': [curated, other, third]}, votes, True)['p']]
    assert order(0, 4) == ['curated', 'other', 'third']           # below PHOTO_LIKES_MIN_VOTES
    assert order(0, 5) == ['other', 'curated', 'third']
    assert order(10, 11) == ['curated', 'other', 'third']         # within PHOTO_LIKES_MIN_MARGIN
    assert order(10, 12, 13) == ['third', 'other', 'curated']
    monkeypatch.setenv('PHOTO_LIKES_MIN_VOTES', '1')
    assert order(0, 1) == ['curated', 'other', 'third']           # margin still applies
    monkeypatch.setenv('PHOTO_LIKES_MIN_MARGIN', '1')
    assert order(0, 1) == ['other', 'curated', 'third']


def test_like_response_does_not_wait_for_the_photo_analysis(shared_store, venue, monkeypatch):
    pid, photos = venue
    analysed = []
    monkeypatch.setattr(likes, 'analyze_photo', lambda place, photo: analysed.append(photo['url']) or {
        'photo_url': photo['url'], 'source_url': photo['source_url'], 'attributes': {'color_temp': 'cool'}, 'method': 'fixture'})
    tasks = BackgroundTasks()
    result = change_like(pid, LikeIn(photo_id=photo_id(photos[1]), liked=True), 'browser:' + 'a' * 64, tasks)
    assert result['like_count'] == 1 and analysed == [] and len(tasks.tasks) == 1
    tasks.tasks[0].func(*tasks.tasks[0].args)
    assert analysed == [photos[1]['url']]
    assert likes.evidence_for({pid: photos[1]})[pid]['attributes']['color_temp'] == 'cool'
    unliked = change_like(pid, LikeIn(photo_id=photo_id(photos[1]), liked=False), 'browser:' + 'a' * 64, BackgroundTasks())
    assert unliked['like_count'] == 0


def test_concurrent_retries_do_not_create_duplicate_votes(shared_store, venue):
    pid, photos = venue
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda _: likes.set_like(pid, photos[0], 'same-browser', True), range(9)))
    assert all(r['like_count'] == 1 for r in results)
    totals, enabled = likes.snapshot([pid], 'same-browser')
    assert enabled and totals[pid, photo_id(photos[0])] == {'liked': True, 'like_count': 1}
    assert likes.set_like(pid, photos[0], 'same-browser', False)['like_count'] == 0
    assert likes.set_like(pid, photos[0], 'same-browser', False)['like_count'] == 0


def test_account_deletion_removes_only_its_votes_and_blocks_inflight_recreation(shared_store, venue):
    pid, photos = venue
    identity = 'account:' + str(uuid.uuid4())
    likes.set_like(pid, photos[0], identity, True)
    likes.set_like(pid, photos[1], identity, True)
    likes.set_like(pid, photos[0], 'another-account', True)
    assert likes.remove_voter(identity) is True
    assert likes.remove_voter(identity) is True  # Account-deletion retry is safe.
    totals, _ = likes.snapshot([pid], identity)
    assert totals == {(pid, photo_id(photos[0])): {'like_count': 1, 'liked': False}}
    with pytest.raises(likes.RevokedVoter):
        likes.set_like(pid, photos[1], identity, True)
    with likes.connection() as conn:
        assert conn.execute('SELECT count(*) FROM photo_likes WHERE voter_hash=%s', (likes.voter_hash(identity),)).fetchone()[0] == 0


def test_recommendation_reads_use_one_store_round_trip(shared_store, venue, monkeypatch):
    pid, photos = venue
    likes.set_like(pid, photos[1], 'browser:' + 'b' * 64, True)
    likes.ensure_evidence(pid, photos[1])
    reads = []
    original = likes._read
    monkeypatch.setattr(likes, '_read', lambda ids, identity: reads.append(list(ids)) or original(ids, identity))
    with TestClient(app) as client:
        detail, _ = evaluation(client, pid)
    assert reads == [[pid]]                                   # snapshot() + evidence_for() shared one query
    assert detail['photos'][0]['like_count'] == 1 and detail['scoring']['evidence_photo_url'] == photos[1]['url']
    assert likes.evidence_for({pid: photos[1]})[pid]['attributes'] == {'color_temp': 'cool'}
    assert len(reads) == 2                                    # standalone evidence lookups still query


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


def test_origin_allowlist_trusts_the_forwarded_scheme_only_from_a_trusted_proxy(monkeypatch):
    monkeypatch.setenv('PHOTO_LIKES_DATABASE_URL', 'postgresql://unused@localhost:1/unused')
    monkeypatch.setenv('PHOTO_LIKES_COOKIE_SECRET', 'test-only-cookie-secret-' * 3)
    monkeypatch.delenv('PHOTO_LIKES_ORIGINS', raising=False)
    monkeypatch.delenv('FORWARDED_ALLOW_IPS', raising=False)
    monkeypatch.delenv('VERCEL', raising=False)
    same = {'Origin': 'https://photospot.litaandd.com', 'X-Forwarded-Proto': 'https'}
    with TestClient(app, base_url='http://photospot.litaandd.com') as client:
        # Plain uvicorn behind an unknown peer: the header is client-controlled, so the scheme stays http.
        assert client.post('/preview/photo-likes/session', json={}, headers=same).status_code == 403
        monkeypatch.setenv('FORWARDED_ALLOW_IPS', '10.0.0.1,testclient')
        ok = client.post('/preview/photo-likes/session', json={}, headers=same)
        assert ok.status_code == 200 and 'Secure' in ok.headers['set-cookie']
        assert client.post('/preview/photo-likes/session', json={},
                           headers={**same, 'Origin': 'https://photospot-nu.vercel.app'}).status_code == 403
        monkeypatch.delenv('FORWARDED_ALLOW_IPS')
        monkeypatch.setenv('VERCEL', '1')
        assert client.post('/preview/photo-likes/session', json={}, headers=same).status_code == 200
        monkeypatch.delenv('VERCEL')
        monkeypatch.setenv('PHOTO_LIKES_ORIGINS', 'https://photospot.litaandd.com')
        assert client.post('/preview/photo-likes/session', json={}, headers={'Origin': 'https://photospot.litaandd.com'}).status_code == 200
        assert client.post('/preview/photo-likes/session', json={}, headers={'Origin': 'https://evil.example'}).status_code == 403


def test_daily_caps_limit_new_anonymous_voters_and_likes_per_address(shared_store, venue, monkeypatch):
    pid, photos = venue
    monkeypatch.setattr(routes, 'daily_limits', [('/preview/photo-likes/session', SlidingWindow(2, window_s=86400)),
                                                 ('/preview/photo-likes/', SlidingWindow(1, window_s=86400))])
    browsers = [TestClient(app) for _ in range(3)]
    assert [c.post('/preview/photo-likes/session', json={}).status_code for c in browsers] == [200, 200, 429]
    assert browsers[0].post('/preview/photo-likes/session', json={}).status_code == 200   # existing cookie, no new voter
    like = {'photo_id': photo_id(photos[0]), 'liked': True}
    assert browsers[0].post('/preview/photo-likes/' + pid, json=like).status_code == 200
    second = browsers[1].post('/preview/photo-likes/' + pid, json={**like, 'photo_id': photo_id(photos[1])})
    assert second.status_code == 429 and '내일' in second.json()['title'] and int(second.headers['retry-after']) > 0
    assert browsers[0].post('/preview/photo-likes/' + pid, json={**like, 'liked': False}).status_code == 200  # unlike is free


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


def test_identity_survives_thumbnail_size_change_and_ties_are_stable(monkeypatch):
    monkeypatch.delenv('PHOTO_LIKES_MIN_VOTES', raising=False)
    monkeypatch.delenv('PHOTO_LIKES_MIN_MARGIN', raising=False)
    first = {'url': 'thumb-1', 'original_url': 'original', 'source_url': 'source'}
    second = {'url': 'thumb-2', 'source_url': 'other'}
    assert photo_id(first) == photo_id({**first, 'url': 'different-size'})
    ranked = likes.rank({'p': [first, second]}, {}, True)['p']
    assert [p['url'] for p in ranked] == ['thumb-1', 'thumb-2']
    ranked = likes.rank({'p': [first, second]}, {('p', photo_id(second)): {'like_count': 4, 'liked': True}}, True)['p']
    assert [p['url'] for p in ranked] == ['thumb-1', 'thumb-2'] and ranked[1]['like_count'] == 4
    ranked = likes.rank({'p': [first, second]}, {('p', photo_id(second)): {'like_count': 5, 'liked': True}}, True)['p']
    assert ranked[0]['url'] == 'thumb-2'


def test_schema_contains_no_profile_or_raw_browser_data():
    text = Path(likes.__file__).with_suffix('.sql').read_text(encoding='utf-8')
    assert 'PRIMARY KEY (place_id, photo_id, voter_hash)' in text
    assert 'analytics_events' in text
    assert not any(field in text for field in ('birth_date', 'client_ip', 'cookie_token', 'user_agent', 'user_id'))


def test_analytics_events_are_stored_without_identifiers(shared_store):
    with TestClient(app) as client:
        response = client.post('/preview/events', json={'event': 'share_click', 'route': '/result', 'session_id': 'abcdefgh1234',
                                                        'utm': {'utm_source': 'kakao'}, 'props': {'target': 'kakao'}})
        assert response.status_code == 204
    with likes.connection() as conn:
        rows = conn.execute('SELECT event, route, session_id, utm, props FROM analytics_events').fetchall()
        columns = {r[0] for r in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='analytics_events'")}
    assert rows == [('share_click', '/result', 'abcdefgh1234', {'utm_source': 'kakao'}, {'target': 'kakao'})]
    assert columns == {'id', 'created_at', 'event', 'route', 'session_id', 'utm', 'props'}


def test_prune_removes_rows_past_the_published_retention(shared_store):
    likes.migrate()
    with likes.connection() as conn:
        conn.execute("INSERT INTO photo_likes (place_id, photo_id, voter_hash, created_at) VALUES "
                     "('p', 'old', 'v1', now() - interval '13 months'), ('p', 'kept', 'v2', now() - interval '11 months')")
        conn.execute("INSERT INTO analytics_events (event, route, session_id, created_at) VALUES "
                     "('save', '/x', 'abcdefgh1234', now() - interval '91 days'), ('save', '/x', 'abcdefgh1234', now() - interval '89 days')")
    assert likes.prune() == (1, 1)
    with likes.connection() as conn:
        assert [r[0] for r in conn.execute('SELECT photo_id FROM photo_likes')] == ['kept']
        assert conn.execute('SELECT count(*) FROM analytics_events').fetchone()[0] == 1


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
