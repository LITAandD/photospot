from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient

from api import public_place_info as info
from api.catalog_recommendations import recommend
from api.preview import app, PreviewIn
from pipeline import place_catalog as catalog, catalog_photos as photos
from tests.test_catalog_photos import image_page


def test_public_photos_rank_before_limit_and_detail_is_public(tmp_path, monkeypatch):
    path = tmp_path / 'browse.sqlite3'
    monkeypatch.setenv('PLACE_CATALOG_DB', str(path))
    catalog.import_response('seoul', {'elements': [
        {'type': 'node', 'id': n, 'lat': 37.5796 + n * .001, 'lon': 126.977,
         'tags': {'name': f'Museum {n}', 'tourism': 'museum'}} for n in range(1, 16)]})
    rows = catalog.search(37.5796, 126.977, 5000)
    far = rows[-1]['id']
    photo = photos.reusable_image(image_page())
    photos.store_photos([{**photo, 'place_id': far, 'match_method': 'reviewed:branch', 'match_ref': 'test', 'priority': 1}], path)
    body = PreviewIn(visit_date=date(2026, 11, 12), limit=2)
    result = recommend(body, {}, public_browse=True)['recommendations']
    assert result.items[0].place_id == far and result.items[0].cover_photo
    assert result.items[1].cover_photo is None
    with TestClient(app) as client:
        listing = client.get('/preview/browse?city=seoul&visit_date=2026-11-12')
        assert listing.status_code == 200 and len(listing.json()['items']) == 12
        assert listing.json()['items'][0]['place_id'] == far
        detail = client.get(f'/preview/browse/{far}?city=seoul&visit_date=2026-11-19')
        assert detail.status_code == 200 and 'set-cookie' not in detail.headers
        data = detail.json()
        assert data['place_id'] == far and data['browse_origin']['label'] == '서울 종로·북촌'
        assert data['facts'] == [] and 'scoring' not in data and 'photos' not in data
        assert data['cover_photo']['license'] and data['cover_photo']['source_url']
        assert client.get(f'/preview/browse/{far}?city=busan&visit_date=2026-11-12').status_code == 404
        assert client.get(f'/preview/browse/{uuid4()}?city=seoul&visit_date=2026-11-12').status_code == 404
        assert client.get('/preview/browse/invalid?city=seoul&visit_date=2026-11-12').status_code == 422


def test_facts_require_current_review_and_allowlisted_source(monkeypatch):
    fact = dict(kind='admission', label='입장료', value='무료', source_label='공식 안내',
                source_url='https://www.gogung.go.kr/gogung/main/contents.do?menuNo=800011', checked_at='2026-11-12')
    monkeypatch.setattr(info, 'reviewed', lambda: {'p': [fact]})
    assert info.facts_for('p', on=date(2026, 11, 12)) == [fact]
    assert info.facts_for('p', on=date(2026, 11, 11)) == []
    assert info.facts_for('p', on=date(2026, 12, 13)) == []
    assert info.facts_for('unknown', on=date(2026, 11, 12)) == []
    fact['source_url'] = 'https://www.gogung.go.kr.example.com/info'
    assert info.facts_for('p', on=date(2026, 11, 12)) == []


def test_background_describes_only_the_reviewed_cover(monkeypatch):
    cover = {'url': 'https://example.com/photo.jpg', 'source_url': 'https://example.com/source'}
    evidence = {'photo_url': cover['url'], 'source_url': cover['source_url'],
                'checked_at': '2026-11-12', 'attributes': {'form': 'curved'}}
    assert info.facts_for('unknown', evidence, cover) == []
    monkeypatch.setattr(info, 'REVIEWS', {'unknown': {**evidence, 'scene_usable': True, 'form': 'curved'}})
    facts = info.facts_for('unknown', evidence, cover)
    assert len(facts) == 1 and facts[0]['value'] == '곡선이 있는 구조'
    assert facts[0]['label'] == '대표사진 배경'
    assert info.facts_for('unknown', evidence, {**cover, 'url': 'https://example.com/other.jpg'}) == []
    assert info.facts_for('unknown', evidence, None) == []


def test_hakrim_current_official_hours_and_future_coverage():
    from pipeline import place_hours
    pid = 'bd8e38de-2cf0-51b4-8485-d8d709c4ecc4'
    entry = place_hours.reviewed_hours()[pid]
    place = {'id': pid, 'name': '학림다방', 'lat': entry.lat, 'lng': entry.lng}
    current = place_hours.hours_for(place, '2026-11-12', date(2026, 11, 12))
    assert not current['stale'] and '10:00' in current['summary']
    assert current['source_url'].startswith('https://korean.visitseoul.net/')
    expired = place_hours.hours_for(place, '2026-12-14', date(2026, 12, 14))
    assert expired['stale'] and '확인 필요' in expired['summary']
