
import pytest

from pipeline import official_cafe_photos as official, catalog_photos as photos, place_catalog as catalog
from pipeline import cafe_photos


def place(**changes):
    return {'id': 'p', 'name': '스타벅스', 'category': 'cafe', 'lat': 37.5, 'lng': 127.0, 'address': None, **changes}


def branch(**changes):
    return {'s_biz_code': '1234', 's_name': '테스트', 'lat': '37.5', 'lot': '127.0',
            'doro_address': '서울특별시 강남구 테스트로 10',
            'defaultimage': '/upload/store/2026/10/[1234]_a.jpg',
            'etcimage': '/upload/store/2026/10/[1234]_b.jpg,/upload/store/2026/10/[1234]_a.jpg', **changes}


def test_matching_requires_brand_branch_distance_and_address_agreement():
    assert official.match_branches([place()], [branch()])
    for p in [place(name='다른 카페'), place(name='스타벅스 다른점'), place(category='heritage'),
              place(lat=37.51), place(address='서울특별시 강남구 테스트로 20')]:
        assert not official.match_branches([p], [branch()])
    assert official.match_branches([place(name='Starbucks 테스트점', address='테스트로 10')], [branch()])


def test_generic_brand_at_two_close_branches_is_not_assigned():
    stores = [branch(), branch(s_biz_code='5678', s_name='다른', lat='37.5002')]
    assert not official.match_branches([place()], stores)
    assert official.match_branches([place(name='스타벅스 테스트점')], stores)
    assert not official.match_branches([place()], [branch(hlytag='4')])


def test_duplicate_catalog_nodes_do_not_duplicate_branch_photos():
    result = official.match_branches([place(), place(id='other', lat=37.5001)], [branch()])
    assert list(result) == ['p']


def test_only_unique_official_branch_paths_are_accepted():
    row = branch(etcimage=','.join([
        '/upload/store/2026/10/[1234]_a.jpg', '/upload/store/2026/10/1234_b.jpg',
        '/upload/store/2026/10/[9999]_c.jpg', '/common/logo.jpg',
        'https://other.example/1234.jpg', '/upload/store/../../../private.jpg',
        '/upload/store/../../private/1234_secret.jpg']))
    urls = official.image_urls(row)
    assert len(urls) == 2
    assert all(url.startswith(official.CDN + '/upload/store/') for url in urls)
    records = official.records_for('p', row)
    assert records[0]['license'] == '© Starbucks Korea' and records[0]['license_url'] == ''
    assert records[0]['source_url'].endswith('in_biz_cd=1234')


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / 'cafes.sqlite3'
    monkeypatch.setenv('PLACE_CATALOG_DB', str(path))
    catalog.import_response('seoul', {'elements': [
        {'type': 'node', 'id': 1, 'lat': 37.5, 'lon': 127.0, 'tags': {'name': '스타벅스', 'amenity': 'cafe'}}]}, path)
    with catalog.connect(path) as conn: pid = conn.execute('SELECT id FROM places').fetchone()[0]
    photos.store_photos(official.records_for(pid, branch()), path)
    return path, pid


def test_official_gallery_survives_commons_refresh_and_enriches_name(db):
    path, pid = db
    photos.prune_completed_links([pid], set(), path)
    assert len(photos.photos_for([pid], path)[pid]) == 2
    assert photos.photos_for([pid], path)[pid][0]['title'] == '스타벅스 테스트 · 공식 매장 사진'
    assert photos.photo_counts_for([pid], path)[pid] == 2
    rows = catalog.search(37.5, 127, 1000, path=path)
    assert rows[0]['name'] == '스타벅스 테스트'
    assert rows[0]['address'] == '서울특별시 강남구 테스트로 10'
    with catalog.connect(path) as conn:
        assert conn.execute('SELECT name FROM places').fetchone()[0] == '스타벅스'
        conn.execute("UPDATE places SET name='다른 카페'")
    assert not photos.photos_for([pid], path)
    assert not photos.photo_counts_for([pid], path)


def test_reviewed_multiple_images_are_deduplicated_and_survive_regular_import(monkeypatch):
    entry = {'place_id': 'p', 'branch': '학림다방', 'lat': 37.5, 'lng': 127,
             'file': 'File:Main.jpg', 'extra_files': ['File:Other.jpg', 'File:Main.jpg'], 'verified_by': 'caption'}
    monkeypatch.setattr(cafe_photos, 'reviewed', lambda: [entry])
    p = place(tags='{}', name='학림다방')
    class NoNetwork:
        def get(self, *args): raise AssertionError('Reviewed files do not need name searches')
    result = photos.candidates(NoNetwork(), [p], include_categories=False)
    assert set(result) == {'File:Main.jpg', 'File:Other.jpg'}
    assert result['File:Main.jpg']['p'][2] < result['File:Other.jpg']['p'][2]
