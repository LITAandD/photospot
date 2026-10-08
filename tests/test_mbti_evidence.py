from datetime import date
import json

import pytest

from api.catalog_scoring import explanation
from pipeline import catalog_mbti as mbti, catalog_visitors as visitors, place_catalog as catalog
from scripts.export_catalog import export


@pytest.fixture
def places(tmp_path, monkeypatch):
    path = tmp_path / 'catalog.sqlite3'
    monkeypatch.setenv('PLACE_CATALOG_DB', str(path))
    catalog.import_response('seoul', {'elements': [
        {'type': 'node', 'id': n, 'lat': 37.57, 'lon': 126.97+n*.001,
         'tags': {'name': f'Cafe {n}', 'amenity': 'cafe'}} for n in range(1,4)]})
    return catalog.search(37.57, 126.97, 5000)


def annual(place, count):
    return dict(place_id=place['id'], place_source=place['source_url'], place_name=place['name'],
                year=2025, visitors=count, unit_id=place['id'], unit_label=place['name'],
                source_url='https://example.org/annual', source_label='Annual fixture',
                published_at='2026-07-31', count_basis='admissions')


def description(place, excerpt='정교한 디테일이 있는 공간'):
    return dict(place_id=place['id'], place_source=place['source_url'], place_name=place['name'],
                lat=place['lat'], lng=place['lng'], source_url='https://pcmap.place.naver.com/restaurant/123/information',
                provider='naver', label='Test space description', excerpt=excerpt, scope='space', checked_at='2026-10-08')


def test_annual_rank_is_catalog_wide_and_fixed_to_2025(places):
    rows = [annual(p, n) for p, n in zip(places, (100, 1000, 0))]
    assert visitors.import_annual(rows) == 3
    context, ranked = visitors.rankings()
    assert context['period_start'] == '2025-01' and context['period_end'] == '2025-12'
    assert context['measured_count'] == 3
    assert ranked[places[1]['id']]['rank'] == 1 and ranked[places[1]['id']]['percentile'] == 1
    assert ranked[places[2]['id']]['visitors'] == 0 and ranked[places[2]['id']]['percentile'] == 0
    assert visitors.rankings(as_of=date(2026, 7, 30))[1] == {}
    assert visitors.rankings(as_of=date(2027, 1, 1))[1][places[1]['id']]['visitors'] == 1000


@pytest.mark.parametrize('change', [{'year': 2024}, {'visitors': -1}, {'visitors': True},
    {'count_basis': 'reviews'}, {'published_at': '2025-12-31'}, {'published_at': '2027-01-01'},
    {'place_source': 'https://www.openstreetmap.org/node/wrong'}, {'source_url': 'http://example.org/x'}])
def test_annual_import_validates_entire_batch(places, change):
    with pytest.raises(ValueError):
        visitors.import_annual([annual(places[0], 50), {**annual(places[1], 200), **change}])
    assert visitors.rankings()[1] == {}


def test_duplicate_statistical_unit_does_not_inflate_rank_and_export_is_public(places, tmp_path):
    first = annual(places[0], 50)
    visitors.import_annual([first])
    with pytest.raises(ValueError):
        visitors.import_annual([{**annual(places[1], 50), 'unit_id': first['unit_id']}])
    mbti.import_records([description(places[0])])
    target = tmp_path/'export.sqlite3'
    export(target)
    assert visitors.rankings(target)[1][places[0]['id']]['status'] == 'insufficient'
    assert mbti.descriptions_for([places[0]['id']], target)


def test_sn_requires_space_text_and_ignores_photo_guess(places):
    p = places[0]
    def metric(letter, descriptions=None):
        result = explanation({'mbti': f'E{letter}TJ'}, {'attributes': {'place_character': 'detail'}}, p,
                             descriptions=descriptions)
        return next(m for m in result['metrics'] if m['key'] == 'mbti_sn.place_character')
    assert metric('S')['status'] == 'pending'
    mbti.import_records([description(p)])
    records = mbti.descriptions_for([p['id']])[p['id']]
    assert metric('S', records)['points'] == 10
    assert metric('N', records)['points'] == 0
    assert metric('S', records)['sources'][0]['keywords'] == ['디테일', '정교']
    mbti.import_records([description(p, '정교한 디테일. 우주 테마의 공간.')])
    records = mbti.descriptions_for([p['id']])[p['id']]
    assert metric('S', records)['points'] == metric('N', records)['points'] == 5
    assert not mbti.description_character([description(p, '디테일이 없다. 컨셉이 아니다.')])[0]
    assert not mbti.description_character([description(p, '컨셉 설명은 없고 맛이 좋다.')])[0]
    assert not mbti.descriptions_for([p['id']], as_of=date(2026,10,7))


@pytest.mark.parametrize('change', [{'scope': 'food'}, {'lat': 35.1}, {'place_name': 'Wrong branch'},
    {'source_url': 'https://map.naver.com.evil.test/restaurant/123'}, {'source_url': 'https://blog.naver.com/x/123'},
    {'source_url': 'https://www.instagram.com/brand/'}, {'checked_at': '2027-01-01'}])
def test_description_requires_exact_venue_and_permitted_source(places, change):
    with pytest.raises(ValueError):
        mbti.import_records([description(places[0]), {**description(places[1]), **change}])
    assert mbti.descriptions_for([p['id'] for p in places]) == {}


def test_tf_mixed_and_unknown_are_distinct_and_jp_does_not_add_points():
    for place, expected in [({'category': 'cafe'}, (10,0)), ({'category': 'park'}, (0,10)),
                            ({'category': 'park', 'tags': {'building': 'yes'}}, (5,5)),
                            ({'category': 'attraction'}, (None,None))]:
        for letter, points in zip('TF', expected):
            scores = [explanation({'mbti': f'EN{letter}{jp}'}, None, place) for jp in 'JP']
            assert scores[0] == scores[1]
            metric = next(m for m in scores[0]['metrics'] if m['key'] == 'mbti_tf.space_nature')
            assert metric['points'] == points
            assert metric['status'] == ('pending' if points is None else 'scored')
