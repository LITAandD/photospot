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
        assert set(listing.json()) == {'items', 'browse_origin'}
        assert set(listing.json()['items'][0]) == {'place_id', 'place_name', 'distance_m', 'cover_photo', 'hours', 'public_facts'}
        assert 'likes_enabled' not in listing.json()['items'][0]['cover_photo']
        detail = client.get(f'/preview/browse/{far}?city=seoul&visit_date=2026-11-19')
        assert detail.status_code == 200 and 'set-cookie' not in detail.headers
        data = detail.json()
        assert data['place_id'] == far and data['browse_origin']['label'] == '서울 종로·북촌'
        assert data['facts'] == [] and 'scoring' not in data and 'photos' not in data
        assert data['cover_photo']['license'] and data['cover_photo']['source_url']
        assert client.get(f'/preview/browse/{far}?city=busan&visit_date=2026-11-12').status_code == 404
        assert client.get(f'/preview/browse/{uuid4()}?city=seoul&visit_date=2026-11-12').status_code == 404
        assert client.get('/preview/browse/invalid?city=seoul&visit_date=2026-11-12').status_code == 422

        from deploy.vercel.frontend import register_spa_routes, register_seo_routes
        from fastapi import FastAPI
        from xml.etree import ElementTree
        entry = tmp_path / 'index.html'
        entry.write_text('<html><head><title>포토스팟</title><link rel="canonical" href="/"><meta property="og:url" content="/"><meta property="og:image" content="/og.png"></head></html>', encoding='utf-8')
        site = FastAPI()
        register_spa_routes(site, entry)
        register_seo_routes(site)
        with TestClient(site) as web:
            canonical = f'https://photospot.litaandd.com/browse/{far}?city=seoul'
            locations = [e.text for e in ElementTree.fromstring(web.get('/sitemap.xml').content).findall('.//{*}loc')]
            assert locations.count(canonical) == 1
            assert len(locations) == len(set(locations))
            assert {u for u in locations if '/browse?city=' in u} == {
                f'https://photospot.litaandd.com/browse?city={city}' for city in info.ORIGINS}
            assert all(web.get(url).status_code == 200 for url in locations if '/browse' in url)
            assert web.get(canonical).status_code == 200
            assert '<title>Museum 15 · 서울 종로·북촌 · 포토스팟</title>' in web.get(canonical).text
            for visit in ('2026-11-12', '2026-11-19'):
                page = web.get(canonical + '&date=' + visit + '&utm_source=share')
                assert page.status_code == 200 and f'rel="canonical" href="{canonical}"' in page.text
                assert f'property="og:url" content="{canonical}&amp;date={visit}"' in page.text
                assert 'property="og:image" content="/og.png"' in page.text
                redirect = web.get(f'/browse/{far}?date={visit}', follow_redirects=False)
                assert redirect.status_code == 302 and redirect.headers['location'] == f'/browse/{far}?city=seoul&date={visit}'
            assert web.get(canonical.replace('seoul', 'busan')).status_code == 404
            listed = web.get('/browse?city=jeju&date=2026-11-22')
            assert 'href="https://photospot.litaandd.com/browse?city=jeju"' in listed.text
            assert 'content="https://photospot.litaandd.com/browse?city=jeju&amp;date=2026-11-22"' in listed.text
            assert '제주 제주시 둘러보기' in listed.text


def test_metadata_escapes_catalog_text_and_preserves_generic_share_image():
    from deploy.vercel.frontend import page_meta, dated_url
    html = '<head><title>old</title><meta property="og:title" content="old"><meta property="og:image" content="/og.png"></head>'
    result = page_meta(html, 'https://example.org/browse?city=seoul', 'https://example.org/browse?city=seoul&date=2026-11-22',
                       r'A <script> & "B" \1', 'Address <tag>')
    assert '<script>' not in result and '&lt;script&gt;' in result and '&quot;B&quot;' in result
    assert r'\1' in result and 'content="/og.png"' in result
    assert dated_url('/browse?city=seoul', '2026-02-30') == '/browse?city=seoul'


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


def test_hakrim_current_official_hours_and_future_coverage(monkeypatch):
    from pipeline import place_hours
    pid = 'bd8e38de-2cf0-51b4-8485-d8d709c4ecc4'
    entry = place_hours.ReviewedHours(place_id=pid, place_name='학림다방', branch_name='학림', lat=37.5, lng=127,
        address='테스트로 1', week=['10:00–22:00'] * 7, checked_at=date(2026, 11, 12),
        source_url='https://korean.visitseoul.net/restaurants/test', provider='official')
    monkeypatch.setattr(place_hours, 'reviewed_hours', lambda: {pid: entry})
    place = {'id': pid, 'name': '학림다방', 'lat': entry.lat, 'lng': entry.lng}
    current = place_hours.hours_for(place, '2026-11-12', date(2026, 11, 12))
    assert not current['stale'] and '10:00' in current['summary']
    assert current['source_url'].startswith('https://korean.visitseoul.net/')
    expired = place_hours.hours_for(place, '2026-12-14', date(2026, 12, 14))
    assert expired['stale'] and '확인 필요' in expired['summary']
