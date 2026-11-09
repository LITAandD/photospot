"""요청 간 장소별 정적 값 캐시: 카탈로그 파일이 바뀌면 비우고, 결과는 캐시 없이 계산한 값과 같다."""
from datetime import date

from api import catalog_media, scoring_cache
from api.catalog_scoring import explanation
from api.preview import PreviewIn, evaluate
from pipeline import catalog_photos as photos, place_catalog as catalog
from pipeline.catalog_mbti import description_character, space_nature
from pipeline.place_editorial import resolve_elements
from tests.test_catalog_photos import image_page

PROFILE = dict(gender='female', height_cm=165, pc_season='summer_cool', body_type='natural', mbti='ENFP')


def make_catalog(tmp_path, monkeypatch, name='places.sqlite3'):
    path = tmp_path / name
    monkeypatch.setenv('PLACE_CATALOG_DB', str(path))
    catalog.import_response('seoul', {'elements': [
        {'type': 'node', 'id': 1, 'lat': 37.5, 'lon': 127.0, 'tags': {'name': '한강공원', 'leisure': 'park'}},
        {'type': 'node', 'id': 2, 'lat': 37.501, 'lon': 127.0, 'tags': {'name': '벽돌 카페', 'amenity': 'cafe', 'building': 'yes', 'material': 'brick'}},
        {'type': 'node', 'id': 3, 'lat': 37.502, 'lon': 127.0, 'tags': {'name': '미술관', 'tourism': 'museum', 'building': 'yes'}}]}, path)
    with catalog.connect(path) as conn:
        ids = {r['osm_id']: r['id'] for r in conn.execute('SELECT id, osm_id FROM places')}
        places = {r['id']: dict(r) for r in conn.execute('SELECT * FROM places')}
    photos.store_photos([{**photos.reusable_image(image_page()), 'place_id': ids[1],
                          'match_method': 'reviewed:branch', 'match_ref': 'test', 'priority': 1}], path)
    return path, ids, places


def test_photo_lists_are_cached_per_place_and_copied(tmp_path, monkeypatch):
    path, ids, _ = make_catalog(tmp_path, monkeypatch)
    scoring_cache.clear()
    calls = []
    real = photos.photos_for
    monkeypatch.setattr(photos, 'photos_for', lambda wanted, *a, **k: calls.append(list(wanted)) or real(wanted, *a, **k))
    first = catalog_media.photos_for([ids[1], ids[2]])
    assert list(first) == [ids[1]] and calls == [[ids[1], ids[2]]]
    first[ids[1]][0]['url'] = 'https://example.org/mutated.jpg'          # 호출부가 바꿔도
    second = catalog_media.photos_for([ids[2], ids[1], ids[3]])
    assert second[ids[1]][0]['url'].startswith('https://upload.wikimedia.org/')   # 캐시는 그대로
    assert calls[1:] == [[ids[3]]]                                                  # 새 장소만 다시 읽는다
    assert catalog_media.photo_counts_for(ids.values()) == {ids[1]: 1} and len(calls) == 2


def test_cache_is_dropped_when_the_catalog_file_changes(tmp_path, monkeypatch):
    path, ids, _ = make_catalog(tmp_path, monkeypatch)
    scoring_cache.clear()
    assert ids[2] not in catalog_media.photos_for([ids[2]])
    photos.store_photos([{**photos.reusable_image(image_page()), 'place_id': ids[2],
                          'match_method': 'reviewed:branch', 'match_ref': 'test', 'priority': 1}], path)
    assert len(catalog_media.photos_for([ids[2]])[ids[2]]) == 1                       # 파일이 바뀌면 다시 읽는다
    other = make_catalog(tmp_path, monkeypatch, 'other.sqlite3')[1]
    assert other[1] in catalog_media.photos_for([other[1]]) and ids[2] not in catalog_media.photos_for([ids[2]])


def test_brand_photo_switch_applies_on_top_of_the_cache(tmp_path, monkeypatch):
    path, ids, _ = make_catalog(tmp_path, monkeypatch)
    photos.store_photos([{**photos.reusable_image(image_page()), 'place_id': ids[2], 'license': '© Brand Korea', 'license_url': '',
                          'match_method': 'reviewed:branch', 'match_ref': 'test', 'priority': 1}], path)   # 재사용 허락 없는 공식 사진
    monkeypatch.delenv('ALLOW_OFFICIAL_BRAND_PHOTOS', raising=False)
    scoring_cache.clear()
    assert ids[2] not in catalog_media.photos_for([ids[2]])
    monkeypatch.setenv('ALLOW_OFFICIAL_BRAND_PHOTOS', '1')
    assert [p['license'] for p in catalog_media.photos_for([ids[2]])[ids[2]]] == ['© Brand Korea']
    monkeypatch.delenv('ALLOW_OFFICIAL_BRAND_PHOTOS')
    assert ids[2] not in catalog_media.photos_for([ids[2]])
    assert len(scoring_cache.store('photos')) == 1                                     # 전환해도 다시 읽지 않는다


def test_scoring_features_and_elements_match_direct_computation(tmp_path, monkeypatch):
    _, ids, places = make_catalog(tmp_path, monkeypatch)
    scoring_cache.clear()
    descriptions = [{'source_url': 'https://map.naver.com/p/entry/place/1', 'label': '네이버 지도', 'checked_at': '2026-10-01',
                     'excerpt': '디테일이 섬세한 공간'}]
    for place in places.values():
        character, sources, nature, note, nature_sources = scoring_cache.scoring_features(place, descriptions)
        assert (character, sources) == description_character(descriptions)
        assert (nature, note, nature_sources) == space_nature(place)
        assert scoring_cache.elements_for(place) == resolve_elements(place)
        assert scoring_cache.place_elements(place) == set(resolve_elements(place)['elements'])
    # 두 번째 호출은 복사본: 바꿔도 다음 호출 결과가 그대로다.
    cafe = places[ids[2]]
    scoring_cache.elements_for(cafe)['elements'].append('fire')
    assert scoring_cache.elements_for(cafe) == resolve_elements(cafe)
    scoring_cache.scoring_features(cafe, descriptions)[4][0]['label'] = 'changed'
    assert scoring_cache.scoring_features(cafe, descriptions)[4] == space_nature(cafe)[2]
    # 설명문이 달라지면(검토일 갱신) 다시 계산한다.
    newer = [{**descriptions[0], 'checked_at': '2026-10-20', 'excerpt': '컨셉이 뚜렷한 공간'}]
    assert scoring_cache.scoring_features(cafe, newer)[0] == 'concept'
    assert scoring_cache.scoring_features(cafe, descriptions)[0] == 'detail'
    assert scoring_cache.scoring_features(None, descriptions) == (*description_character(descriptions), *space_nature(None))


def test_explanation_is_unchanged_whether_or_not_features_come_from_the_cache(tmp_path, monkeypatch):
    _, ids, places = make_catalog(tmp_path, monkeypatch)
    place = places[ids[2]]
    evidence = {'attributes': {'color_temp': 'cool', 'form': 'linear'}, 'method': 'photo-color', 'source_url': 'https://example.org/p'}
    direct = explanation(PROFILE, evidence, place, None, None)
    from pipeline import catalog_mbti
    scoring_cache.clear()
    monkeypatch.setattr(catalog_mbti, 'description_character', lambda d: scoring_cache.scoring_features(place, d)[:2])
    monkeypatch.setattr(catalog_mbti, 'space_nature', lambda p: scoring_cache.scoring_features(p, None)[2:])
    assert explanation(PROFILE, evidence, place, None, None) == direct
    assert explanation(PROFILE, evidence, place, None, None) == direct                 # 캐시 적중 후에도 같다


def test_nearby_index_only_returns_candidates_within_reach_and_group():
    index = scoring_cache.NearbyIndex()
    centre = {'lat': 37.5, 'lng': 127.0}
    index.add('cafe', 'a', {**centre, 'id': 'same'})
    index.add('cafe', 'b', {'lat': 37.5012, 'lng': 127.0, 'id': '130m'})           # 약 130m 북쪽
    index.add('cafe', 'c', {'lat': 37.508, 'lng': 127.0, 'id': '890m'})            # 약 890m
    index.add('cafe', 'd', {'lat': 37.52, 'lng': 127.0, 'id': '2.2km'})
    index.add('park', 'a', {**centre, 'id': 'other-group'})
    near_150 = {place['id'] for _, place in index.near('cafe', centre, 150)}
    near_1000 = {place['id'] for _, place in index.near('cafe', centre, 1000)}
    assert {'same', '130m'} <= near_150 and '890m' not in near_150 and '2.2km' not in near_150
    assert {'same', '130m', '890m'} <= near_1000 and '2.2km' not in near_1000
    assert 'other-group' not in near_1000 and {p['id'] for _, p in index.near('park', centre, 150)} == {'other-group'}


def test_evaluation_results_are_identical_across_warm_and_cold_cache(tmp_path, monkeypatch):
    make_catalog(tmp_path, monkeypatch)
    scoring_cache.clear()
    query = PreviewIn(profile=PROFILE, visit_date=date(2026, 10, 10), lat=37.5, lng=127.0, radius_m=3000)
    cold = evaluate(query)
    warm = evaluate(query)
    assert cold['recommendations'] == warm['recommendations'] and cold['places'] == warm['places']
    assert [i.place_id for i in warm['recommendations'].items]
    assert scoring_cache.store('photos')                                            # 사진 목록이 남아 있다
