"""Behavioral bounds: work follows returned rows, without changing rights or ranking."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from datetime import date
from threading import Event

import pytest
from fastapi.testclient import TestClient

from api import catalog_bridge, catalog_recommendations as rec, scoring_cache as cache, schemas
from api.preview import app, PreviewIn
from pipeline import catalog_photos as photos, place_catalog as catalog
from tests.test_scoring_cache import make_catalog
from tests.test_catalog_photos import image_page

D = date(2026, 11, 25)


def test_catalog_identity_checked_once_per_scope_and_reset_after_exception(monkeypatch):
    calls = []
    monkeypatch.setattr(cache, 'catalog_version', lambda: calls.append(1) or ('test', 1))
    with pytest.raises(ValueError), cache.catalog_scope():
        for _ in range(100):
            with cache.catalog_scope():
                assert cache.memo('test', 'x', lambda: 1) == 1
        raise ValueError('interrupted')
    assert len(calls) == 1
    with cache.catalog_scope():
        cache.store('test')
    cache.store('test')
    assert len(calls) == 3


def test_next_operation_sees_new_photo_after_catalog_write(tmp_path, monkeypatch):
    path, ids, _ = make_catalog(tmp_path, monkeypatch)
    from api.catalog_media import photos_for
    with cache.catalog_scope():
        assert not photos_for([ids[2]])
    photos.store_photos([{**photos.reusable_image(image_page()), 'place_id': ids[2],
                         'match_method': 'reviewed:branch', 'match_ref': 'test', 'priority': 1}], path)
    with cache.catalog_scope():
        assert photos_for([ids[2]])[ids[2]]


def test_concurrent_catalog_versions_do_not_mix_request_stores(monkeypatch):
    version = ContextVar('test_catalog_version', default='outside')
    monkeypatch.setattr(cache, 'catalog_version', lambda: (version.get(),))
    first, second = Event(), Event()
    def older():
        version.set('old')
        with cache.catalog_scope():
            cache.store('photos')['same-id'] = 'old-photo'
            first.set()
            assert second.wait(5)
            return cache.store('photos')['same-id']
    def newer():
        assert first.wait(5)
        version.set('new')
        with cache.catalog_scope():
            cache.store('photos')['same-id'] = 'new-photo'
            second.set()
            return cache.store('photos')['same-id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(older), pool.submit(newer)
        assert a.result() == 'old-photo' and b.result() == 'new-photo'
    assert cache.store('photos') == {}


def test_stop_deduplication_at_limit_and_only_resize_returned_photos(tmp_path, monkeypatch):
    make_catalog(tmp_path, monkeypatch)
    yielded, thumbs = [], []
    original, thumb = rec.unique_places, rec.cover_thumbnail
    def traced(*a, **kw):
        for row in original(*a, **kw):
            yielded.append(row[0]['id'])
            yield row
    monkeypatch.setattr(rec, 'unique_places', traced)
    monkeypatch.setattr(rec, 'cover_thumbnail', lambda p: thumbs.append(p['url']) or thumb(p))
    body = PreviewIn(visit_date=D, lat=37.5, lng=127, limit=1)
    result = rec.recommend(body, {}, detail_ids=set(), gallery_ids=set())
    assert len(yielded) == len(result['recommendations'].items) == 1
    assert len(thumbs) == sum(i.cover_photo is not None for i in result['recommendations'].items)
    assert result['places'] == {}


def test_summaries_match_existing_saved_display_without_scoring(tmp_path, monkeypatch):
    path, ids, _ = make_catalog(tmp_path, monkeypatch)
    # Saved records have historically included inactive rows; preserve that contract.
    with catalog.connect(path) as conn:
        conn.execute('UPDATE places SET active=0 WHERE id=?', (ids[2],))
    wanted = [ids[3], ids[2], 'missing', ids[1]]
    body = PreviewIn(visit_date=D, place_ids=wanted)
    old = rec.recommend(body, {}, nearby=False, detail_ids=set(wanted), gallery_ids=set())['places']
    expected = [schemas.Bookmark(place_id=pid, name=old[pid].name, address=old[pid].address,
                                cover_photo=old[pid].photos[0] if old[pid].photos else None).model_dump(mode='json')
                for pid in wanted if pid in old]
    def forbidden(*a, **kw):
        raise AssertionError('saved display must not calculate preference scores')
    monkeypatch.setattr(rec, 'explanation', forbidden)
    with TestClient(app) as client:
        response = client.post('/preview/places/summary', json={'place_ids': wanted, 'visit_date': str(D)})
        assert response.status_code == 200 and response.json() == expected
        assert 'set-cookie' not in response.headers and 'no-store' in response.headers['cache-control']
        assert client.post('/preview/places/summary', json={'place_ids': [], 'visit_date': str(D)}).json() == []
        for extra in ({'profile': {}}, {'place_ids': ['x'] * 101}, {'place_ids': ['x' * 65]}):
            assert client.post('/preview/places/summary', json={'place_ids': wanted, 'visit_date': str(D), **extra}).status_code == 422


def test_summaries_preserve_official_address_and_viewer_votes(tmp_path, monkeypatch):
    _, ids, _ = make_catalog(tmp_path, monkeypatch)
    seen = []
    monkeypatch.setattr('pipeline.place_hours.hours_for', lambda p, d: {'address': '확인된 공식 주소'})
    from api import photo_likes
    monkeypatch.setattr(photo_likes, 'read', lambda places, identity: seen.append((list(places), identity)) or ({}, [], False))
    value = catalog_bridge.preview_summaries([ids[1], ids[1], 'missing'], D, 'browser-test')
    assert len(value) == 1 and value[0]['address'] == '확인된 공식 주소'
    assert seen == [([ids[1]], 'browser-test')]
    assert value[0]['cover_photo']['license_url']


def test_summaries_keep_rights_gate_and_follow_live_cover_votes(tmp_path, monkeypatch):
    path, ids, _ = make_catalog(tmp_path, monkeypatch)
    from api import photo_likes
    second = {**photos.reusable_image(image_page('File:Second.jpg')), 'place_id': ids[1],
              'url': 'https://upload.wikimedia.org/wikipedia/commons/a/ab/Second.jpg',
              'original_url': 'https://upload.wikimedia.org/wikipedia/commons/a/ab/Second.jpg',
              'source_url': 'https://commons.wikimedia.org/wiki/File:Second.jpg',
              'match_method': 'reviewed:branch', 'match_ref': 'test', 'priority': 9}
    denied = {**second, 'place_id': ids[2], 'license': 'All rights reserved', 'license_url': ''}
    photos.store_photos([second, denied], path)
    monkeypatch.delenv('ALLOW_OFFICIAL_BRAND_PHOTOS', raising=False)
    votes = {}
    monkeypatch.setattr(photo_likes, 'read', lambda *_: (votes, [], True))
    a = catalog_bridge.preview_summaries([ids[1], ids[2]], D)
    assert a[1]['cover_photo'] is None
    assert a[0]['cover_photo']['url'] != second['url']
    votes[(ids[1], photo_likes.photo_id(second))] = {'like_count': 10, 'liked': True}
    b = catalog_bridge.preview_summaries([ids[1], ids[2]], D)
    assert b[0]['cover_photo']['url'] == second['url']
    assert b[0]['cover_photo']['liked'] and b[1]['cover_photo'] is None


def test_summaries_do_not_disguise_unavailable_catalog_as_empty_saves(tmp_path, monkeypatch):
    monkeypatch.setenv('PLACE_CATALOG_DB', str(tmp_path / 'empty.sqlite3'))
    with TestClient(app) as client:
        assert client.post('/preview/places/summary', json={'place_ids': ['saved'], 'visit_date': str(D)}).status_code == 503
        assert client.post('/preview/places/summary', json={'place_ids': [], 'visit_date': str(D)}).json() == []
