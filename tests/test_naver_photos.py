import copy
import json

import pytest

from pipeline import naver_photos as naver, place_catalog as catalog, catalog_photos


@pytest.fixture
def setup(tmp_path):
    entries = json.loads(naver.MANIFEST.read_text(encoding='utf-8'))
    path = tmp_path / 'places.sqlite3'
    with catalog.connect(path) as conn:
        for entry in entries['places']:
            kind, osm_id = entry['place_source'].rsplit('/', 2)[-2:]
            conn.execute('INSERT INTO places(id,osm_type,osm_id,name,category,lat,lng,address,source_url,tags,fetched_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (entry['place_id'], kind, int(osm_id), entry['name'], 'cafe', entry['lat'], entry['lng'], entry.get('catalog_address', entry['address']), entry['place_source'], '{}', '2026-10-08'))
    return path, entries


def test_import_export_counts_and_commons_refresh_preserves_reviewed_images(setup):
    path, entries = setup
    expected = {'places': len(entries['places']), 'photos': sum(len(e['photos']) for e in entries['places'])}
    assert naver.apply(path) == naver.apply(path) == expected
    ids = [e['place_id'] for e in entries['places']]
    catalog_photos.prune_completed_links(ids, set(), path)
    photos = catalog_photos.photos_for(ids, path)
    assert sum(map(len, photos.values())) == expected['photos']
    for entry in entries['places']:
        assert catalog_photos.photo_counts_for([entry['place_id']], path)[entry['place_id']] == len(entry['photos'])
        photo = photos[entry['place_id']][0]
        assert photo['source_url'] == entry['source_url']
        assert photo['attribution'] == entry['author']
        assert photo['license_url'] == entry['license_url']
        assert photo['keep_aspect_ratio']


@pytest.mark.parametrize('field,value', [
    ('license_url', 'https://creativecommons.org/licenses/by-nc-nd/2.0/kr/'),
    ('license_url', 'https://creativecommons.org.evil.test/licenses/by/4.0/'),
    ('license', 'Public domain'), ('author', ''), ('name', 'Other branch'),
    ('license_evidence', ''),
    ('lat', 33.0), ('reviewed_at', '2099-01-01'),
    ('source_url', 'https://blog.naver.com/author'),
])
def test_invalid_rights_or_branch_never_replace_existing_photos(setup, tmp_path, field, value):
    path, entries = setup
    expected = naver.apply(path)
    bad = copy.deepcopy(entries)
    bad['places'][-1][field] = value
    manifest = tmp_path / 'bad.json'
    manifest.write_text(json.dumps(bad), encoding='utf-8')
    with pytest.raises(ValueError): naver.apply(path, manifest)
    with catalog.connect(path) as conn:
        assert conn.execute('SELECT count(*) FROM catalog_photos').fetchone()[0] == expected['photos']


def test_withdrawn_photos_removed_and_branch_changes_hide_stale_photos(setup, tmp_path):
    path, entries = setup
    naver.apply(path)
    first = entries['places'][0]
    with catalog.connect(path) as conn:
        conn.execute('UPDATE places SET lat=33 WHERE id=?', (first['place_id'],))
    assert not catalog_photos.photos_for([first['place_id']], path)
    assert not catalog_photos.photo_counts_for([first['place_id']], path)
    manifest = tmp_path / 'empty.json'
    manifest.write_text('{"places": []}', encoding='utf-8')
    assert naver.apply(path, manifest) == {'places': 0, 'photos': 0}
