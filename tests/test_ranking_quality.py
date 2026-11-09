"""Ranking quality: photo/curation tier first, low-value OSM nodes and chains hidden, duplicates merged."""
from datetime import date
import json

import pytest

from api import catalog_recommendations as recommendations
from api.catalog_recommendations import closed_on_visit, public_name
from api.catalog_scoring import catalog_card
from api.preview import PreviewIn, evaluate
from pipeline import catalog_photos as photos, place_catalog as catalog, place_quality as quality

VISIT = date(2026, 11, 10)
BASE = (37.5796, 126.977)


def node(n, name, dlat=0.0, dlng=0.0, **tags):
    return {'type': 'node', 'id': n, 'lat': BASE[0] + dlat, 'lon': BASE[1] + dlng, 'tags': {'name': name, **tags}}


def photo(place, path, title='Branch'):
    photos.store_photos([dict(place_id=place['id'], file_title=f'File:{title}.jpg',
        url=f'https://upload.wikimedia.org/wikipedia/commons/a/ab/{title}.jpg',
        original_url=f'https://upload.wikimedia.org/wikipedia/commons/a/ab/{title}.jpg',
        source_url=f'https://commons.wikimedia.org/wiki/File:{title}.jpg', license='CC BY-SA 4.0',
        license_url='https://creativecommons.org/licenses/by-sa/4.0/', attribution='Photographer',
        width=1000, height=700, description='Exact place photo', match_method='osm:image', match_ref=f'File:{title}.jpg', priority=0)], path)


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / 'places.sqlite3'
    monkeypatch.setenv('PLACE_CATALOG_DB', str(path))
    return path


@pytest.mark.parametrize('name,tags,category,reason', [
    ('제68호어린이공원', {'leisure': 'park'}, 'park', 'neighbourhood_park'),
    ('노형근린공원', {'leisure': 'park'}, 'park', 'neighbourhood_park'),
    ('별양1소공원', {'leisure': 'park'}, 'park', 'neighbourhood_park'),
    ('놀이터', {'leisure': 'playground'}, 'park', 'sports_facility'),
    ('8호 공원', {'leisure': 'park'}, 'park', 'neighbourhood_park'),
    ('봉은테니스장', {'leisure': 'pitch'}, 'park', 'sports_facility'),
    ('강서체육공원', {'leisure': 'park'}, 'park', 'sports_facility'),
    ('화장실', {'amenity': 'toilets'}, 'park', 'fixture'),
    ('망원1동 공영주차장', {'leisure': 'park'}, 'park', 'fixture'),
    ('삼성물산(주)', {'amenity': 'theatre'}, 'cultural_venue', 'corporate_name'),
    ('목동아파트 14단지 공원', {'leisure': 'park'}, 'park', 'apartment_complex'),
    # Kept: real destinations whose names merely resemble the patterns.
    ('민주공원', {'leisure': 'park'}, 'park', None),
    ('(주)솔숲수목원', {'leisure': 'garden'}, 'park', None),
    ('(주)현갤러리', {'tourism': 'gallery'}, 'gallery', None),
    ('국립체육박물관', {'tourism': 'museum'}, 'museum', None),
    ('KT&G 상상마당', {'amenity': 'arts_centre'}, 'cultural_venue', None),
    ('커피내리는 버스정류장', {'amenity': 'cafe'}, 'cafe', None),
    ('주식회사 프리츠(양재점)', {'amenity': 'cafe'}, 'cafe', None),
    ('경복궁', {'historic': 'palace'}, 'heritage', None),
])
def test_low_value_osm_nodes_are_named_by_pattern(name, tags, category, reason):
    assert quality.low_value_reason(name, tags, category) == reason


def test_photo_or_curation_overrides_low_value_but_not_franchise():
    park = {'name': '문래근린공원', 'tags': {'leisure': 'park'}, 'category': 'park'}
    assert quality.recommendation_exclusion(park) == 'neighbourhood_park'
    assert quality.recommendation_exclusion(park, photographed=True) is None
    chain = {'name': '이디야커피 종로점', 'tags': '{}', 'category': 'cafe'}
    assert quality.recommendation_exclusion(chain, photographed=True) == 'franchise_chain'
    assert quality.recommendation_exclusion(chain, curated=True) is None
    keep = next(url for url, entry in quality.dining_curation.entries().items() if entry.get('starbucks_keep'))
    assert quality.recommendation_exclusion({'name': '스타벅스', 'tags': '{}', 'category': 'cafe', 'source_url': keep}) is None
    assert quality.is_franchise('Cafe', {'brand:wikidata': 'Q37158'})
    assert quality.is_franchise('coffee shop', {'brand:en': 'Twosome Place'})
    assert not quality.is_franchise('테라로사 커피공장', {})
    assert not quality.is_franchise('블루보틀 성수', {})
    assert quality.recommendation_exclusion({'name': '이디야 갤러리', 'tags': '{}', 'category': 'gallery'}) is None


@pytest.mark.parametrize('name,expected', [
    ('한국가구박물관 ( Korea Furniture Museum)', '한국가구박물관'),
    ('삼릉공원 / 서울 선릉과 정릉', '삼릉공원'),
    ('GAMDO(감도)', '감도'),
    ('Art center nabi', 'Art center nabi'),
    ('Leeum', 'Leeum'),
    ('주식회사 프리츠(양재점)', '프리츠 양재점'),
    ('(주)커피빈코리아 선정릉역점', '커피빈코리아 선정릉역점'),
    ('KB아트홀(강남)', 'KB아트홀 강남'),
    ('윤동주기념관 (521)', '윤동주기념관'),
    ('수변 공원', '수변 공원'),
])
def test_public_name_prefers_clean_korean_names(name, expected):
    assert public_name({'id': 'x', 'name': name, 'lat': BASE[0], 'lng': BASE[1], 'source_url': 'https://www.openstreetmap.org/node/1', 'category': 'cafe', 'tags': '{}'}) == expected


def hours(summary, **changes):
    return {'provider': 'naver', 'schedule_kind': 'regular', 'source_label': 'x', 'source_url': 'https://map.naver.com/p/entry/place/1',
            'checked_at': '2026-11-01', 'stale': False, 'summary': summary, 'weekly_hours': [], 'notes': [], 'address': '', 'branch_name': 'x', **changes}


def test_closed_flag_only_for_confirmed_closing_days():
    assert closed_on_visit(hours('화 정기휴궁 (정규)'))
    assert closed_on_visit(hours('월 휴무 (지도 등록)', provider='openstreetmap'))
    assert closed_on_visit(hours('화 휴점 (공식 날짜별)', provider='official', schedule_kind='dated'))
    assert not closed_on_visit(hours('화 09:00–18:00 (정규)'))
    assert not closed_on_visit(hours('월 휴무 (지도 등록)', stale=True))
    assert not closed_on_visit(hours('등록 운영시간 · 상세 안내 확인', schedule_kind='source_text'))
    assert not closed_on_visit(None)


@pytest.mark.parametrize('season', ['spring_warm', 'summer_cool', 'autumn_warm', 'winter_cool'])
@pytest.mark.parametrize('body', [None, 'straight', 'wave', 'natural'])
def test_type_card_names_best_light_whenever_a_season_is_set(season, body):
    card = catalog_card({'pc_season': season, 'body_type': body})
    assert card.best_light and all(light in {'골든아워 햇빛', '부드러운 자연광', '따뜻한 조명', '차가운 조명·야경'} for light in card.best_light)
    assert not set(card.best_light) & set(card.avoid)
    assert catalog_card({'body_type': 'wave'}).best_light == []


def test_photo_tier_hides_low_value_nodes_and_chains_and_merges_duplicates(db):
    catalog.import_response('seoul', {'elements': [
        node(1, '사진공원', leisure='park'),
        node(2, '누리숲 어린이공원', .002, 0, leisure='park'),
        node(3, '이디야커피 종로점', .001, .001, amenity='cafe'),
        node(4, '한강공원', .003, 0, leisure='park', wikidata='Q1'),
        node(5, '한강공원', .009, 0, leisure='park', wikidata='Q1'),
        node(6, '청계천', 0, .004, natural='water'),
        node(7, '청계천', 0, .012, natural='water'),  # ~700m: same linear feature
        node(8, '골목 카페', .0015, .0015, amenity='cafe'),
        node(9, '(주)제일기획', .002, .002, amenity='theatre'),
        node(10, 'GAMDO(감도)', .0025, .0025, amenity='cafe'),
        node(11, 'KB아트홀', .004, .004, amenity='theatre'),
        node(12, 'KB아트홀(강남)', .0041, .0041, amenity='theatre'),
    ]}, db)
    rows = {p['name']: p for p in catalog.search(*BASE, 5000, path=db)}
    photo(rows['사진공원'], db)
    result = evaluate(PreviewIn(visit_date=VISIT, profile={'mbti': 'INFP'}))
    items = result['recommendations'].items
    names = [i.place_name for i in items]
    assert names[0] == '사진공원' and items[0].cover_photo
    assert items[0].fit_score == 12.5 and items[0].match_basis == 'category'  # category estimate shown, not ordering
    for hidden in ('누리숲 어린이공원', '이디야커피 종로점', '(주)제일기획'):
        assert hidden not in names
    assert names.count('한강공원') == 1 and names.count('청계천') == 1
    assert '감도' in names and sum(n.startswith('KB아트홀') for n in names) == 1
    assert result['recommendations'].missing_inputs == ['퍼스널컬러', '체형']
    cafe = next(i for i in items if i.place_name == '골목 카페')
    assert cafe.hours is None and cafe.time_slot_label == '운영시간 · 지도에서 확인'
    # Hidden places stay reachable by id for details and bookmarks.
    chain = rows['이디야커피 종로점']
    detail = evaluate(PreviewIn(visit_date=VISIT, place_ids=[chain['id']]))
    assert chain['id'] in detail['places'] and chain['id'] in {i.place_id for i in detail['recommendations'].items}
    assert evaluate(PreviewIn(visit_date=VISIT)).get('recommendations').missing_inputs == ['퍼스널컬러', '체형', 'MBTI']


def test_shared_wikidata_or_gallery_merges_only_the_same_spot(db):
    # 월드컵공원 cluster: OSM tags every sub-park with the umbrella wikidata id and the pipeline gives them one gallery,
    # but they are distinct parks 1-2km apart (하늘공원 972m, 난지천공원 1185m, 난지한강공원 1487m from 평화의공원).
    catalog.import_response('seoul', {'elements': [
        node(1, '평화의공원', leisure='park', wikidata='Q11263863'),
        node(2, '하늘공원', .0087, 0, leisure='park', wikidata='Q11263863'),
        node(3, '난지천공원', 0, .0134, leisure='park', wikidata='Q11263863'),
        node(4, '난지한강공원', -.0134, 0, leisure='park', wikidata='Q11263863'),
        node(5, '월드컵공원 평화광장', .0004, 0, leisure='park', wikidata='Q11263863'),  # 45m: the same spot, another node
        node(6, '난지 전망대', .0005, .0134, tourism='viewpoint'),                      # 55m from 난지천공원, one shared photo
    ]}, db)
    rows = {p['name']: p for p in catalog.search(*BASE, 5000, path=db)}
    for name in ('평화의공원', '하늘공원', '난지천공원', '난지한강공원', '월드컵공원 평화광장'):
        for title in ('Worldcup-1', 'Worldcup-2', 'Worldcup-3'): photo(rows[name], db, title)
    photo(rows['난지 전망대'], db, 'Worldcup-1')
    names = [i.place_name for i in evaluate(PreviewIn(visit_date=VISIT))['recommendations'].items]
    assert all(name in names for name in ('평화의공원', '하늘공원', '난지천공원', '난지한강공원', '난지 전망대'))
    assert '월드컵공원 평화광장' not in names and len(names) == 5


def test_prefix_names_merge_only_the_same_kind_or_an_unphotographed_annex(db):
    catalog.import_response('seoul', {'elements': [
        node(1, '남산', natural='peak'), node(2, '남산서울타워', .001, 0, tourism='attraction'),          # 110m, both photographed
        node(3, '탑골공원', 0, .005, leisure='park'), node(4, '탑골공원 팔각정', .0002, .005, tourism='attraction'),  # 22m, annex without photos
        node(5, '세종문화회관', .005, 0, amenity='arts_centre'), node(6, '세종문화회관 대극장', .0052, 0, amenity='arts_centre'),
    ]}, db)
    rows = {p['name']: p for p in catalog.search(*BASE, 5000, path=db)}
    for name in ('남산', '남산서울타워', '탑골공원', '세종문화회관', '세종문화회관 대극장'): photo(rows[name], db, name)
    names = [i.place_name for i in evaluate(PreviewIn(visit_date=VISIT))['recommendations'].items]
    assert '남산' in names and '남산서울타워' in names
    assert '탑골공원' in names and '탑골공원 팔각정' not in names
    assert sum(n.startswith('세종문화회관') for n in names) == 1


def test_confirmed_closing_day_is_demoted_within_its_tier_and_flagged(db, monkeypatch):
    catalog.import_response('seoul', {'elements': [node(1, '경복궁', historic='palace'), node(2, '창덕궁', .005, 0, historic='palace')]}, db)
    rows = {p['name']: p for p in catalog.search(*BASE, 5000, path=db)}
    for row in rows.values(): photo(row, db, row['name'])
    seen = {}
    def fake_hours(place, visit):
        seen[place['name']] = visit
        return hours('화 정기휴궁 (정규)') if place['name'] == '경복궁' else None
    monkeypatch.setattr(recommendations, 'hours_for', fake_hours)
    items = evaluate(PreviewIn(visit_date=VISIT))['recommendations'].items
    assert [i.place_name for i in items] == ['창덕궁', '경복궁']  # nearer palace is closed that day
    assert items[1].hours.summary == '화 정기휴궁 (정규)' and seen['경복궁'] == VISIT
    assert any('휴무일' in note for note in evaluate(PreviewIn(visit_date=VISIT, place_ids=[rows['경복궁']['id']]))['places'][rows['경복궁']['id']].visit_notes)


def test_empty_profile_orders_by_photo_then_popularity_not_distance(db, monkeypatch):
    from pipeline import cafe_popularity as popularity
    monkeypatch.setattr(popularity, 'kst_today', lambda: VISIT)
    catalog.import_response('seoul', {'elements': [
        node(1, '투썸플레이스 종로점', amenity='cafe'), node(2, '가까운 카페', .0005, 0, amenity='cafe'),
        node(3, '인기 카페', .002, 0, amenity='cafe'), node(4, '사진 카페', .004, 0, amenity='cafe')]}, db)
    rows = {p['name']: p for p in catalog.search(*BASE, 5000, path=db)}
    photo(rows['사진 카페'], db)
    popular = rows['인기 카페']
    popularity.import_observations([dict(place_id=popular['id'], place_name=popular['name'], lat=popular['lat'], lng=popular['lng'],
        metric='naver_reviews', value=500, source_url='https://map.naver.com/p/entry/place/123', checked_at=VISIT.isoformat(),
        scope='Verified exact cafe branch')], db)
    items = evaluate(PreviewIn(visit_date=VISIT))['recommendations'].items
    # No profile: photographed place, then the popular branch, then by distance; the chain is hidden.
    assert [i.place_name for i in items] == ['사진 카페', '인기 카페', '가까운 카페']
    assert all(i.fit_score is None for i in items)
    assert json.loads(rows['투썸플레이스 종로점']['tags']) == {'amenity': 'cafe'}
