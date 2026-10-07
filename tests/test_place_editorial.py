from datetime import date
import json

from api.preview import PreviewIn, evaluate
from pipeline import place_catalog as catalog
from pipeline import catalog_photos
from pipeline.place_editorial import resolve_elements, in_ring, official_photos_for


def place(name='', lat=37.57, lng=126.98, category='cafe', **tags):
    return {'name': name, 'lat': lat, 'lng': lng, 'category': category, 'tags': json.dumps(tags),
            'source_url': 'https://www.openstreetmap.org/node/1'}


def test_gwanaksan_and_yeonjudae_use_documented_fire_not_rock_fallback():
    for name in ['관악산', '연주대']:
        p = resolve_elements(place(name, 37.445, 126.965, 'scenic', natural='rock'))
        assert p['elements'] == ['fire'] and p['basis'] == 'traditional'
        assert any('history.go.kr' in s['url'] for s in p['sources'])


def test_named_place_rules_do_not_leak_to_namesakes_or_nearby_cafes():
    for p in [place('관악산', 35.15, 129.16), place('관악산 카페', 37.445, 126.965)]:
        assert resolve_elements(p)['elements'] == []


def test_jamsil_region_overrides_generic_park_and_respects_real_boundary():
    p = resolve_elements(place('잠실근린공원', 37.5060893, 127.0837172, 'park'))
    assert p['elements'] == ['water'] and p['basis'] == 'regional'
    assert any('relation/' in s['url'] for s in p['sources'])
    assert resolve_elements(place('카페', 37.506, 127.084))['elements'] == ['water']
    assert resolve_elements(place('카페', 37.538, 127.084))['elements'] == []
    assert resolve_elements(place('잠실', 35.15, 129.16))['elements'] == []


def test_polygon_handles_concavity_without_bounding_box_leakage():
    ring = [[0, 0], [2, 0], [2, 1], [1, 1], [1, 2], [0, 2], [0, 0]]
    assert in_ring(0.5, 1.5, ring)
    assert not in_ring(1.5, 1.5, ring)


def test_landscape_interpretation_and_unknown_are_explicit():
    park = resolve_elements(place('동네공원', category='park'))
    assert park['elements'] == ['wood'] and park['basis'] == 'landscape'
    assert '직접 논한 풍수 문헌은 아직' in park['explanation']
    unknown = resolve_elements(place('자료 없는 카페'))
    assert unknown['basis'] == 'unassigned' and not unknown['elements']
    cafe = resolve_elements(place('널담은공간', 37.5782788, 126.9798532))
    assert cafe['elements'] == ['wood', 'earth'] and cafe['basis'] == 'landscape'


def test_official_branch_photos_survive_commons_refresh_without_fake_license(tmp_path):
    pid = '318a9d29-0e41-5748-a04d-5a920049f923'
    photos = official_photos_for([pid])[pid]
    assert len(photos) == len({p['url'] for p in photos}) == 7
    assert all('img_kbg_' in p['url'] and 'img_hbc_' not in p['url'] for p in photos)
    assert all(p['license'] == '© 널담' and p['license_url'] is None and p['keep_aspect_ratio'] for p in photos)
    db = tmp_path / 'places.sqlite3'
    catalog_photos.prune_completed_links([pid], set(), db)
    assert catalog_photos.photos_for([pid], db)[pid] == photos


def test_source_backed_deficient_element_filter_does_not_change_base_fit(tmp_path, monkeypatch):
    monkeypatch.setenv('PLACE_CATALOG_DB', str(tmp_path / 'places.sqlite3'))
    catalog.import_response('seoul', {'elements': [
        {'type': 'node', 'id': 1, 'lat': 37.445, 'lon': 126.965, 'tags': {'name': '관악산', 'natural': 'peak'}},
        {'type': 'node', 'id': 2, 'lat': 37.506, 'lon': 127.084, 'tags': {'name': '잠실 카페', 'amenity': 'cafe'}},
        {'type': 'node', 'id': 3, 'lat': 37.55, 'lon': 126.98, 'tags': {'name': '일반공원', 'leisure': 'park'}},
    ]})
    base = PreviewIn(visit_date=date(2026, 10, 6), radius_m=50000, profile={'body_type': 'natural'})
    base_result = evaluate(base)
    base_scores = {i.place_id: i.fit_score for i in base_result['recommendations'].items}
    base.use_saju = True
    base.element = 'water'
    base.percents = {'wood': 25, 'fire': 0, 'earth': 25, 'metal': 25, 'water': 25}
    result = evaluate(base)
    items = result['recommendations'].items
    assert len(items) == 1 and items[0].place_name == '관악산'
    assert items[0].recommended_elements == ['fire']
    assert items[0].fit_score == base_scores[items[0].place_id]
    assert result['places'][items[0].place_id].element_profile == items[0].element_profile


def test_curated_landmark_import_preserves_existing_places_and_real_osm_tags(tmp_path):
    from pipeline.curated_landmarks import sync
    db = tmp_path / 'places.sqlite3'
    catalog.import_response('seoul', {'elements': [{'type': 'node', 'id': 1, 'lat': 37.57, 'lon': 126.98,
        'tags': {'name': '기존 카페', 'amenity': 'cafe'}}]}, db)
    sync(db); sync(db)
    assert catalog.metadata(db)['count'] == 2
    with catalog.connect(db) as conn:
        p = dict(conn.execute('SELECT * FROM places WHERE osm_id=3445797247').fetchone())
    assert p['name'] == '연주대' and p['category'] == 'heritage'
    assert json.loads(p['tags']) == {'amenity': 'place_of_worship'}
    assert resolve_elements(p)['elements'] == ['fire']
