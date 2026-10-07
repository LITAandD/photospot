import copy
import json

import pytest

from pipeline import catalog_photos as photos, place_catalog as catalog
from api.preview import PreviewIn, evaluate


def image_page(title='File:Place.jpg'):
    return {'title': title, 'imageinfo': [{
        'mime': 'image/jpeg', 'width': 1800, 'height': 1200,
        'url': 'https://upload.wikimedia.org/wikipedia/commons/a/ab/Place.jpg',
        'thumburl': 'https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Place.jpg/960px-Place.jpg',
        'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Place.jpg',
        'extmetadata': {'LicenseShortName': {'value': 'CC BY-SA 4.0'},
            'LicenseUrl': {'value': '//creativecommons.org/licenses/by-sa/4.0/'},
            'Artist': {'value': '<a href="https://example.org">Photographer</a>'},
            'ImageDescription': {'value': '<p>Real place photo</p>'}}
    }]}


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / 'catalog.sqlite3'
    monkeypatch.setenv('PLACE_CATALOG_DB', str(path))
    catalog.import_response('seoul', {'elements': [
        {'type': 'node', 'id': 1, 'lat': 37.5796, 'lon': 126.977, 'tags': {'name': 'A', 'amenity': 'cafe'}},
        {'type': 'node', 'id': 2, 'lat': 37.58, 'lon': 126.977, 'tags': {'name': 'B', 'leisure': 'park'}}]}, path)
    return path


def test_photo_reference_enrichment_does_not_replace_place_or_bookmark_identity(db):
    before = catalog.search(37.5796, 126.977, 1000, path=db)
    count = photos.import_references({'elements': [
        {'type': 'node', 'id': 1, 'tags': {'wikidata': 'Q123', 'phone': 'private'}},
        {'type': 'node', 'id': 999, 'tags': {'wikidata': 'Q999'}}]}, db)
    assert count == 1
    after = catalog.search(37.5796, 126.977, 1000, path=db)
    assert [p['id'] for p in before] == [p['id'] for p in after]
    assert json.loads(after[0]['tags']) == {'amenity': 'cafe', 'wikidata': 'Q123'}
    assert catalog.metadata(db)['count'] == 2
    with pytest.raises(ValueError): photos.import_references({'remark': 'timeout', 'elements': []}, db)


@pytest.mark.parametrize('value,expected', [
    ('File:Place_with;a_name.jpg', 'File:Place with;a name.jpg'),
    ('Category:Some_place', 'Category:Some place'),
    ('https://commons.wikimedia.org/wiki/File:Place.jpg', 'File:Place.jpg'),
    ('https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Place.jpg/200px-Place.jpg', 'File:Place.jpg'),
    ('https://other.example/Place.jpg', None), ('https://commons.wikimedia.org.evil/wiki/File:A.jpg', None),
    ('File:A.jpg|File:B.jpg', None),
])
def test_only_explicit_commons_references_are_resolved(value, expected):
    assert photos.commons_title(value) == expected


def test_image_metadata_carries_author_source_license_and_dimensions():
    image = photos.reusable_image(image_page())
    assert image['attribution'] == 'Photographer'
    assert image['description'] == 'Real place photo'
    assert image['license_url'] == 'https://creativecommons.org/licenses/by-sa/4.0/'
    assert image['width'] == 1800 and image['height'] == 1200


@pytest.mark.parametrize('mutation', ['unknown-license', 'noncommercial', 'missing-artist', 'svg', 'unsafe-url', 'tiny'])
def test_unusable_or_unverified_images_are_excluded(mutation):
    page = image_page()
    info = page['imageinfo'][0]
    if mutation == 'unknown-license': info['extmetadata']['LicenseUrl']['value'] = ''
    if mutation == 'noncommercial': info['extmetadata']['LicenseUrl']['value'] = 'https://creativecommons.org/licenses/by-nc/4.0/'
    if mutation == 'missing-artist': info['extmetadata'].pop('Artist')
    if mutation == 'svg': info['mime'] = 'image/svg+xml'
    if mutation == 'unsafe-url': info['thumburl'] = 'http://localhost/private'
    if mutation == 'tiny': info['width'] = 32
    assert photos.reusable_image(page) is None


def test_storage_is_idempotent_and_list_detail_share_real_photos(db, monkeypatch):
    place = catalog.search(37.5796, 126.977, 1000, path=db)[0]
    record = {**photos.reusable_image(image_page()), 'place_id': place['id'],
              'match_method': 'wikidata:P18', 'match_ref': 'Q123', 'priority': 10}
    photos.store_photos([record, record], db)
    assert photos.summary(db) == {'photo_links': 1, 'unique_files': 1, 'places_with_photos': 1}
    def fail(*a, **kw): raise AssertionError('App queries must never fetch external metadata')
    monkeypatch.setattr(photos.PublicClient, 'get', fail)
    result = evaluate(PreviewIn(visit_date='2026-10-10', profile={'body_type': 'wave'}))
    item = next(i for i in result['recommendations'].items if i.place_id == place['id'])
    detail = result['places'][place['id']]
    assert item.cover_photo == detail.photos[0]
    assert detail.photos[0].keep_aspect_ratio
    assert detail.photos[0].source_url.startswith('https://commons.wikimedia.org/')
    assert detail.analysis_pending and detail.best_scene is None  # Linking images must not invent analysis.
    assert next(i for i in result['recommendations'].items if i.place_id != place['id']).cover_photo is None


def test_category_pagination_collects_all_direct_files_and_never_brand_images():
    calls = []
    class Client:
        def get(self, endpoint, params):
            calls.append(params)
            if 'cmcontinue' not in params:
                return {'query': {'categorymembers': [{'title': 'File:A.jpg'}]}, 'continue': {'cmcontinue': 'next'}}
            return {'query': {'categorymembers': [{'title': 'File:B.jpg'}]}}
    result = photos.candidates(Client(), [{'id': 'p', 'tags': json.dumps({'wikimedia_commons': 'Category:Place', 'brand:wikidata': 'Q42'})}])
    assert set(result) == {'File:A.jpg', 'File:B.jpg'} and len(calls) == 2
    assert all('p' in matches for matches in result.values())


def test_entity_from_another_branch_is_excluded():
    entity = {'claims': {'P625': [{'mainsnak': {'snaktype': 'value', 'datavalue': {'value': {
        'latitude': 35.1, 'longitude': 129.1, 'globe': 'http://www.wikidata.org/entity/Q2'}}}}]}}
    assert not photos.nearby_entity(entity, {'lat': 37.5, 'lng': 127, 'category': 'cafe'})


def test_completed_refresh_removes_only_stale_links_in_its_place_scope(db):
    places = catalog.search(37.5796, 126.977, 1000, path=db)
    base = {**photos.reusable_image(image_page()), 'match_method': 'wikidata:P18', 'match_ref': 'Q123', 'priority': 10}
    photos.store_photos([{**base, 'place_id': p['id']} for p in places], db)
    photos.prune_completed_links([places[0]['id']], set(), db)
    assert places[0]['id'] not in photos.photos_for([p['id'] for p in places], db)
    assert places[1]['id'] in photos.photos_for([p['id'] for p in places], db)


def test_long_multibyte_titles_are_split_to_avoid_gateway_url_limits():
    batches = list(photos.chunks(['File:' + '가' * 100 + str(i) + '.jpg' for i in range(45)]))
    assert sum(map(len, batches)) == 45
    assert all(len('|'.join(photos.urllib.parse.quote(v) for v in batch)) < 6600 for batch in batches)


def test_timed_out_response_is_retried_and_only_success_is_cached(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from io import BytesIO
    attempts, delays = [], []
    @contextmanager
    def request(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            class InterruptedResponse:
                def read(self, size): raise TimeoutError('interrupted body')
            yield InterruptedResponse()
        else:
            yield BytesIO(b'{"query":{"pages":{}}}')
    monkeypatch.setattr(photos.urllib.request, 'urlopen', request)
    monkeypatch.setattr(photos.time, 'sleep', delays.append)
    client = photos.PublicClient(tmp_path)
    result = client.get(photos.COMMONS, {'action': 'query'})
    assert result == {'query': {'pages': {}}}
    assert len(attempts) == 2 and 30 in delays
    assert len(list(tmp_path.glob('*.json'))) == 1
    assert client.get(photos.COMMONS, {'action': 'query'}) == result
    assert len(attempts) == 2
