import json
import sqlite3

import pytest

from pipeline import place_catalog as catalog, dining_curation as dining
from pipeline.place_categories import group_for
from pipeline.cafe_photos import display_name
from api.catalog_scoring import place_setting
from api.preview import PreviewIn, evaluate


def node(n, name='동네 카페', **tags):
    return {'type': 'node', 'id': n, 'lat': 37.579, 'lon': 126.987,
            'tags': {'name': name, 'amenity': 'cafe', **tags}}


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / 'places.sqlite3'
    monkeypatch.setenv('PLACE_CATALOG_DB', str(path))
    return path


def test_brand_exclusion_survives_refresh_and_preserves_reviewed_branch(db):
    kept = next(e for e in dining.entries().values() if e.get('starbucks_keep') and '/node/' in e['source_url'])
    keep_node = node(int(kept['source_url'].split('/')[-1]), kept['names'][0])
    keep_node.update(lat=kept['lat'], lon=kept['lng'])
    raw = {'elements': [node(1), node(2, 'STARBUCKS'), node(3, '별다방', **{'brand:wikidata':'Q37158'}), keep_node]}
    for _ in range(2):
        assert catalog.import_response('seoul', raw, db) == 2
        with catalog.connect(db) as conn:
            assert {r[0] for r in conn.execute('SELECT osm_id FROM places')} == {1, keep_node['id']}


def test_curated_import_hard_deletes_children_backs_up_and_is_idempotent(db):
    catalog.import_response('seoul', {'elements': [node(1), node(2)]}, db)
    with catalog.connect(db) as conn:
        removed = conn.execute('SELECT id FROM places WHERE osm_id=2').fetchone()[0]
        conn.execute("UPDATE places SET name='스타벅스 일반점' WHERE id=?", (removed,))
        conn.execute('CREATE TABLE catalog_visuals(place_id TEXT PRIMARY KEY, attributes TEXT)')
        conn.execute('INSERT INTO catalog_visuals VALUES (?,?)',(removed,'{}'))
    result = dining.apply(db)
    assert result['deleted_starbucks'] == 1 and result['added'] == 16
    with sqlite3.connect(result['backup']) as backup:
        assert backup.execute('SELECT count(*) FROM places WHERE id=?',(removed,)).fetchone()[0] == 1
    with catalog.connect(db) as conn:
        for table, column in [('places','id'),('region_places','place_id'),('catalog_visuals','place_id')]:
            assert not conn.execute(f'SELECT 1 FROM {table} WHERE {column}=?',(removed,)).fetchone()
    assert dining.apply(db)['added'] == 0
    catalog.import_response('seoul', {'elements': [node(1)]}, db)
    with catalog.connect(db) as conn:
        assert conn.execute('SELECT count(*) FROM places WHERE active=1').fetchone()[0] == 17


def test_bad_snapshot_never_changes_database(db, tmp_path, monkeypatch):
    catalog.import_response('seoul', {'elements': [node(1)]}, db)
    manifest = tmp_path/'bad'/'dining_curation.json'
    manifest.parent.mkdir()
    (manifest.parent/'dining_osm.json').write_text(json.dumps({'elements':[node(99)]}), encoding='utf-8')
    monkeypatch.setattr(dining, 'MANIFEST', manifest)
    with pytest.raises(ValueError, match='unreviewed'):
        dining.apply(db)
    assert catalog.metadata(db)['count'] == 1


def test_bakery_restaurant_filter_evidence_and_refresh_category(db):
    dining.apply(db)
    from datetime import date
    result = evaluate(PreviewIn(visit_date=date.today(), lat=37.579, lng=126.987, radius_m=50000,
                              place_group='cafe', profile={'height_cm':160}))
    items = result['recommendations'].items
    assert any(i.spot_name == '베이커리' for i in items)
    assert any(i.spot_name == '식당' for i in items)
    assert all(i.discovery.curation and not i.discovery.popularity for i in items)
    assert all(i.place_group == 'cafe' for i in items)
    rows = catalog.search(37.579,126.987,50000,path=db)
    london = next(p for p in rows if p['osm_id'] == 13674825136)
    assert display_name(london) == '런던베이글뮤지엄 안국점'
    assert dining.evidence({**london,'lat':35}) is None
    assert group_for('bakery') == group_for('restaurant') == 'cafe'
    for kind in ('bakery','restaurant'):
        assert place_setting({'category':kind,'tags':'{}'}, {})[0] == 'indoor'
    onion = next(e for e in json.loads((dining.MANIFEST.parent/'dining_osm.json').read_text(encoding='utf-8'))['elements'] if e['id']==6507290987)
    catalog.import_response('seoul',{'elements':[onion]},db)
    assert next(p for p in catalog.search(37.579,126.987,5000,path=db) if p['osm_id']==6507290987)['category'] == 'bakery'
