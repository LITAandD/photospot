import copy
import json

import pytest

from api.catalog_media import reusable
from pipeline import kogl_photos as kogl, place_catalog as catalog, catalog_photos


@pytest.fixture
def setup(tmp_path):
    entries = json.loads(kogl.MANIFEST.read_text(encoding='utf-8'))
    path = tmp_path / 'places.sqlite3'
    with catalog.connect(path) as conn:
        for e in entries['places']:
            kind, osm_id = e['place_source'].rsplit('/', 2)[-2:]
            conn.execute('INSERT INTO places(id,osm_type,osm_id,name,category,lat,lng,address,source_url,tags,fetched_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (e['place_id'], kind, int(osm_id), e['name'], 'cafe', e['lat'], e['lng'], e['address'], e['place_source'], '{}', '2026-10-13'))
    return path, entries


def test_kogl_is_reusable_and_survives_commons_refresh(setup):
    path, entries = setup
    expected = {'places': len(entries['places']), 'photos': sum(len(e['photos']) for e in entries['places'])}
    assert kogl.apply(path) == kogl.apply(path) == expected
    ids = [e['place_id'] for e in entries['places']]
    catalog_photos.prune_completed_links(ids, set(), path)
    photos = catalog_photos.photos_for(ids, path)
    assert sum(map(len, photos.values())) == expected['photos']
    assert catalog_photos.photo_counts_for(ids, path) == {pid: len(ps) for pid, ps in photos.items()}
    for e in entries['places']:
        for photo in photos[e['place_id']]:
            assert reusable(photo)
            assert photo['license_url'] == kogl.LICENSE_URL
            assert photo['attribution'] and photo['source_url']
            assert photo['title'] in [p['description'] for p in e['photos']]
    assert not reusable({'license_url': kogl.LICENSE_URL + '?type=4'})
    assert not reusable({'license_url': 'https://www.kogl.or.kr/info/licenseType4.do'})


@pytest.mark.parametrize('field,value', [
    ('license_url', 'https://www.kogl.or.kr/info/licenseType4.do'),
    ('license', '공공누리 제4유형'), ('license_evidence', ''), ('spatial_review', ''),
    ('attribution', ''), ('url', 'https://www.visitbusan.net.evil.test/archive/upload/photo.jpg'),
    ('source_url', 'https://www.visitbusan.net/'),
])
def test_invalid_rights_and_sources_leave_existing_rows_intact(setup, tmp_path, field, value):
    path, entries = setup
    expected = kogl.apply(path)
    invalid = copy.deepcopy(entries)
    invalid['places'][-1]['photos'][0][field] = value
    manifest = tmp_path / 'invalid.json'
    manifest.write_text(json.dumps(invalid), encoding='utf-8')
    with pytest.raises(ValueError): kogl.apply(path, manifest)
    with catalog.connect(path) as conn:
        assert conn.execute('SELECT count(*) FROM catalog_photos').fetchone()[0] == expected['photos']


def test_moved_or_withdrawn_branch_photos_are_not_shown(setup, tmp_path):
    path, entries = setup
    kogl.apply(path)
    first = entries['places'][0]
    with catalog.connect(path) as conn:
        conn.execute('UPDATE places SET lat=33 WHERE id=?', (first['place_id'],))
    assert not catalog_photos.photos_for([first['place_id']], path)
    assert not catalog_photos.photo_counts_for([first['place_id']], path)
    empty = tmp_path / 'empty.json'
    empty.write_text('{"places": []}', encoding='utf-8')
    assert kogl.apply(path, empty) == {'places': 0, 'photos': 0}
