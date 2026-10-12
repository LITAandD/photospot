"""Read-time photo licensing, single-place detail scoring and catalog connection reuse."""
from datetime import date

import pytest

from api import catalog_bridge, catalog_media
from api.preview import PreviewIn, evaluate
from pipeline import catalog_photos as photos, official_cafe_photos as official, place_catalog as catalog
from tests.test_catalog_photos import image_page
from tests.test_official_cafe_photos import branch

PROFILE = dict(gender='female', height_cm=170, pc_season='spring_warm', pc_subtone='light', body_type='wave', mbti='INFP')


@pytest.fixture
def db(tmp_path, monkeypatch):
    from pipeline import dining_curation
    monkeypatch.setattr(dining_curation, 'entries', lambda: {
        'https://www.openstreetmap.org/node/1': {'starbucks_keep': True, 'names': [], 'lat': 37.5, 'lng': 127.0, 'display_name': ''}})
    monkeypatch.delenv('ALLOW_OFFICIAL_BRAND_PHOTOS', raising=False)
    path = tmp_path / 'cafes.sqlite3'
    monkeypatch.setenv('PLACE_CATALOG_DB', str(path))
    catalog.import_response('seoul', {'elements': [
        {'type': 'node', 'id': 1, 'lat': 37.5, 'lon': 127.0, 'tags': {'name': '스타벅스', 'amenity': 'cafe'}},
        {'type': 'node', 'id': 2, 'lat': 37.501, 'lon': 127.0, 'tags': {'name': 'Park', 'leisure': 'park'}},
        {'type': 'node', 'id': 3, 'lat': 37.502, 'lon': 127.0, 'tags': {'name': 'Cafe 3', 'amenity': 'cafe'}}]}, path)
    with catalog.connect(path) as conn:
        ids = {r['osm_id']: r['id'] for r in conn.execute('SELECT id, osm_id FROM places')}
    photos.store_photos(official.records_for(ids[1], branch()), path)           # © Starbucks Korea, no licence URL
    photos.store_photos([{**photos.reusable_image(image_page()), 'place_id': ids[2],
                          'match_method': 'reviewed:branch', 'match_ref': 'test', 'priority': 1}], path)
    return ids


def test_official_brand_photos_without_reuse_licence_are_hidden_by_default(db, monkeypatch):
    brand, park = db[1], db[2]
    assert len(photos.photos_for([brand])[brand]) == 2                           # Stored for provenance.
    assert catalog_media.photos_for([brand, park]) == {park: photos.photos_for([park])[park]}
    assert catalog_media.photo_counts_for([brand, park]) == {park: 1}
    result = evaluate(PreviewIn(visit_date=date(2026, 10, 10), lat=37.5, lng=127.0))
    shown = {i.place_id: i for i in result['recommendations'].items}
    assert shown[brand].cover_photo is None and result['places'][brand].photos == []
    assert shown[brand].discovery.photo_count == 0
    assert all(p.license_url.startswith('https://creativecommons.org/')
               for place in result['places'].values() for p in place.photos)
    # Only with written permission may an operator opt in.
    monkeypatch.setenv('ALLOW_OFFICIAL_BRAND_PHOTOS', '1')
    allowed = evaluate(PreviewIn(visit_date=date(2026, 10, 10), lat=37.5, lng=127.0))
    assert allowed['places'][brand].photos[0].license == '© Starbucks Korea'


def test_editorial_official_photos_follow_the_same_rule(monkeypatch):
    from pipeline.place_editorial import editorial
    pid = editorial()['official_photos'][0]['place_id']
    monkeypatch.delenv('ALLOW_OFFICIAL_BRAND_PHOTOS', raising=False)
    assert pid not in catalog_media.photos_for([pid])
    monkeypatch.setenv('ALLOW_OFFICIAL_BRAND_PHOTOS', '1')
    assert catalog_media.photos_for([pid])[pid]


def test_unlicensed_close_view_cannot_replace_licensed_cover(db, monkeypatch):
    park = db[2]
    original = catalog_media.photos_for([park])[park]
    from pipeline.place_editorial import official_photos_for
    def with_close_view(ids):
        result = official_photos_for(ids)
        if park in ids:
            result[park] = [{**original[0], 'title': 'Interior', 'license_url': None, 'license': 'Copyright',
                            'url': 'https://example.org/unlicensed-interior.jpg'}]
        return result
    monkeypatch.setattr('pipeline.place_editorial.official_photos_for', with_close_view)
    assert photos.photos_for([park])[park][0]['title'] == 'Interior'
    assert catalog_media.photos_for([park])[park] == original


def test_detail_scores_only_the_requested_place_with_identical_result(db):
    for pid in db.values():
        place = catalog_bridge.find(pid)
        for use_saju in (False, True):
            profile = {**PROFILE, 'element': 'wood', 'saju_percents': {'wood': 5, 'fire': 20, 'earth': 25, 'metal': 25, 'water': 25}}
            nearby = catalog_bridge.evaluate(profile, date(2026, 10, 10), lat=place['lat'], lng=place['lng'],
                                             use_saju=use_saju, place_ids=[pid])['places'][pid]
            assert catalog_bridge.detail(profile, date(2026, 10, 10), place, use_saju) == nearby


def test_detail_does_not_scan_the_surrounding_area(db, monkeypatch):
    seen = []
    search = catalog.search
    monkeypatch.setattr(catalog, 'search', lambda *a, **k: seen.append(k.get('nearby')) or search(*a, **k))
    place = catalog_bridge.find(db[2])
    catalog_bridge.detail(PROFILE, date(2026, 10, 10), place)
    assert seen == [False]
    assert [p['id'] for p in catalog.search(place['lat'], place['lng'], 5000, [db[2]], nearby=False)] == [db[2]]


def test_batch_lookups_skip_unknown_and_inactive_places(db):
    with catalog.connect() as conn: conn.execute('UPDATE places SET active=0 WHERE id=?', (db[3],))
    found = catalog_bridge.find_many([db[2], db[3], '00000000-0000-0000-0000-000000000000', db[2]])
    assert list(found) == [db[2]]
    rows = catalog_bridge.bookmark_rows([db[1], db[2]])
    assert rows[db[1]]['cover_photo'] is None and rows[db[2]]['cover_photo']['license'] == 'CC BY-SA 4.0'
    assert catalog_bridge.find_many([]) == {}


def test_catalog_schema_is_created_once_per_file(tmp_path, monkeypatch):
    scripts = []

    class Spy:
        def __init__(self, conn): self.conn = conn
        def executescript(self, sql): scripts.append(sql); return self.conn.executescript(sql)
        def __getattr__(self, name): return getattr(self.conn, name)
        def __setattr__(self, name, value):
            if name == 'conn': object.__setattr__(self, name, value)
            else: setattr(self.conn, name, value)
        def __enter__(self): self.conn.__enter__(); return self
        def __exit__(self, *args): return self.conn.__exit__(*args)

    real = catalog.sqlite3.connect
    monkeypatch.setattr(catalog.sqlite3, 'connect', lambda *a, **k: Spy(real(*a, **k)))
    path = tmp_path / 'once.sqlite3'
    for _ in range(3):
        with catalog.connect(path) as conn: conn.execute('SELECT count(*) FROM places').fetchone()
    assert len(scripts) == 1
    path.unlink()                                                         # A replaced file is initialized again.
    with catalog.connect(path) as conn: assert conn.execute('SELECT count(*) FROM places').fetchone()[0] == 0
    assert len(scripts) == 2


def test_ensure_schema_runs_each_script_once_per_file(tmp_path):
    path = tmp_path / 'extra.sqlite3'
    script = 'CREATE TABLE IF NOT EXISTS extra (x INTEGER);'
    with catalog.connect(path) as conn:
        catalog.ensure_schema(conn, script)
        conn.execute('DROP TABLE extra')
        catalog.ensure_schema(conn, script)                                   # Cached: not re-run.
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='extra'").fetchone()
