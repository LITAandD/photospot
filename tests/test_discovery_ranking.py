from datetime import date, timedelta
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError

from api.preview import PreviewIn, evaluate
from pipeline import cafe_popularity as popularity, catalog_photos as photos, catalog_visuals as visuals, place_catalog as catalog


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / 'places.sqlite3'
    monkeypatch.setenv('PLACE_CATALOG_DB', str(path))
    return path


def seed(db, count=3):
    catalog.import_response('seoul', {'elements': [
        {'type': 'node', 'id': n, 'lat': 37.5796 + n * .0001, 'lon': 126.977,
         'tags': {'name': f'Cafe {n}', 'amenity': 'cafe'}} for n in range(1, count + 1)]}, db)
    return sorted(catalog.search(37.5796, 126.977, 5000, path=db), key=lambda p: p['osm_id'])


def photo(place, path, method='osm:image', ref='File:Branch.jpg'):
    photos.store_photos([dict(place_id=place['id'], file_title='File:Branch.jpg',
        url='https://upload.wikimedia.org/wikipedia/commons/a/ab/Branch.jpg',
        original_url='https://upload.wikimedia.org/wikipedia/commons/a/ab/Branch.jpg',
        source_url='https://commons.wikimedia.org/wiki/File:Branch.jpg', license='CC BY-SA 4.0',
        license_url='https://creativecommons.org/licenses/by-sa/4.0/', attribution='Photographer',
        width=1000, height=700, description='Exact branch photo', match_method=method, match_ref=ref, priority=0)], path)


def observation(place, value=100, **changes):
    return dict(place_id=place['id'], place_name=place['name'], lat=place['lat'], lng=place['lng'],
        metric='naver_reviews', value=value, source_url='https://map.naver.com/p/entry/place/123',
        checked_at=date.today().isoformat(), scope='Verified exact cafe branch', **changes)


def recommend(**kwargs):
    return evaluate(PreviewIn(visit_date=date.today(), profile={'body_type': 'wave'}, **kwargs))


def test_photo_priority_is_applied_before_limit_and_not_inflated_by_image_count(db):
    rows = seed(db, 40)
    photo(rows[-1], db)
    result = recommend(place_group='cafe')
    items = result['recommendations'].items
    assert len(items) == 30 and items[0].place_id == rows[-1]['id']
    assert items[0].cover_photo and items[0].discovery.photo_count == 1
    assert items[1].place_id == rows[0]['id']
    assert all(i.fit_score is None for i in items)  # Attached photo alone is not analysis.
    assert result['places'][items[0].place_id].discovery == items[0].discovery


def test_popular_cafes_rank_within_photo_tier_without_altering_fit(db, monkeypatch):
    rows = seed(db)
    for row in rows[:2]: photo(row, db)
    popularity.import_observations([observation(rows[0], 10), observation(rows[1], 1000), observation(rows[2], 99999)], db)
    monkeypatch.setattr(popularity, 'fetch_naver', lambda *_: pytest.fail('Recommendation must use local observations'))
    items = recommend()['recommendations'].items
    assert [i.place_id for i in items] == [rows[1]['id'], rows[0]['id'], rows[2]['id']]
    assert all(i.fit_score is None and i.scoring.score is None for i in items)
    assert items[0].discovery.popularity[0].value == 1000
    assert items[0].links.naver_map_url.endswith('/123')


def analyzed_photo(place, attrs, path):
    photo(place, path)
    attached = photos.photos_for([place['id']], path)[place['id']][0]
    visuals.store(place['id'], attached, attrs, 'test reviewed photo', path)


RANKING_PROFILE = dict(height_cm=160, pc_season='spring_warm', pc_subtone='light', body_type='wave', mbti='INFP')


def test_evaluation_count_then_fit_rank_all_candidates_before_limit(db):
    rows = seed(db, 40)
    photo(rows[0], db)
    analyzed_photo(rows[-3], {'form': 'curved'}, db)
    analyzed_photo(rows[-2], {'color_temp': 'warm', 'brightness': 'bright_soft', 'saturation': 'muted', 'form': 'curved'}, db)
    analyzed_photo(rows[-1], {'color_temp': 'cool', 'brightness': 'high_contrast', 'saturation': 'mid', 'form': 'linear'}, db)
    result = evaluate(PreviewIn(visit_date=date.today(), profile=RANKING_PROFILE))
    items = result['recommendations'].items
    assert len(items) == 30
    assert [i.place_id for i in items[:4]] == [rows[-2]['id'], rows[-1]['id'], rows[-3]['id'], rows[0]['id']]
    assert [sum(m.status == 'scored' for m in i.scoring.metrics) for i in items[:4]] == [5, 5, 2, 1]
    assert items[0].fit_score > items[1].fit_score
    assert items[2].fit_score == 43.5  # 40 earned out of the fixed total of 92.
    assert items[1].fit_score < items[2].fit_score  # More evaluated items win even with lower fit.
    scored = [m.points for m in items[1].scoring.metrics if m.status == 'scored']
    assert 0 in scored and any(p < 0 for p in scored)  # Both count as evaluated.
    assert all(result['places'][i.place_id].scoring == i.scoring for i in items)


def test_number_of_evaluated_items_is_not_weight_sum(db):
    rows = seed(db)
    analyzed_photo(rows[0], {'form': 'curved'}, db)  # 2 items, 40 weight, 43.5 fit.
    analyzed_photo(rows[1], {'brightness': 'bright_soft', 'saturation': 'muted'}, db)  # 3 items, 22 weight, higher fit.
    analyzed_photo(rows[2], {'color_temp': 'cool', 'form': 'linear'}, db)  # 3 items, 68 weight, lower fit.
    items = evaluate(PreviewIn(visit_date=date.today(), profile=RANKING_PROFILE))['recommendations'].items
    assert [i.place_id for i in items] == [rows[1]['id'], rows[2]['id'], rows[0]['id']]
    assert [i.scoring.evaluated_weight for i in items] == [22, 68, 40]


def test_zero_score_is_evaluated_and_beats_unrated_photo(db):
    rows = seed(db, 2)
    with catalog.connect(db) as conn:
        conn.execute("UPDATE places SET category='heritage' WHERE id=?", (rows[0]['id'],))
    photo(rows[0], db)
    items = evaluate(PreviewIn(visit_date=date.today(), profile={'height_cm': 171}))['recommendations'].items
    assert [i.place_id for i in items] == [rows[1]['id'], rows[0]['id']]
    assert items[0].fit_score == 0 and items[1].fit_score is None


def test_photo_priority_never_bypasses_distance_group_or_deficit_filter(db):
    rows = seed(db)
    for row in rows: photo(row, db)
    with catalog.connect(db) as conn:
        conn.execute("UPDATE places SET tags=? WHERE id=?", (json.dumps({'material': 'wood'}), rows[1]['id']))
        conn.execute('UPDATE places SET lat=35.1587, lng=129.1604 WHERE id=?', (rows[2]['id'],))
    response = recommend(use_saju=True, element='wood',
        percents={'wood': 0, 'fire': 25, 'earth': 25, 'metal': 25, 'water': 25}, place_ids=[rows[2]['id']])
    assert [i.place_id for i in response['recommendations'].items] == [rows[1]['id']]
    assert rows[2]['id'] in response['places']  # Saved detail stays accessible.
    assert recommend(place_group='festival')['recommendations'].items == []


def test_stale_future_and_missing_signals_do_not_fake_popularity(db):
    rows = seed(db)
    entry = observation(rows[0], 0)
    popularity.import_observations([entry], db)
    assert popularity.popularity_for([rows[0]['id']], db)[rows[0]['id']][0]['value'] == 0
    assert popularity.popularity_for([rows[0]['id']], db, date.today() + timedelta(days=91)) == {}
    assert popularity.popularity_for([rows[0]['id']], db, date.today() - timedelta(days=1)) == {}
    item = next(i for i in recommend()['recommendations'].items if i.place_id == rows[1]['id'])
    assert item.discovery.popularity == [] and item.cover_photo is None
    assert popularity.popularity_score([]) == popularity.popularity_score([{'metric': 'naver_reviews', 'value': 0}])


def test_import_is_atomic_idempotent_branch_checked_and_never_replaced_by_old_data(db):
    rows = seed(db)
    good = observation(rows[0], 100)
    popularity.import_observations([good, good], db)
    old = {**good, 'checked_at': (date.today() - timedelta(days=1)).isoformat(), 'value': 5}
    popularity.import_observations([old], db)
    assert popularity.popularity_for([rows[0]['id']], db)[rows[0]['id']][0]['value'] == 100
    with pytest.raises(ValueError):
        popularity.import_observations([observation(rows[1]), {**good, 'lat': 35.1}], db)
    assert rows[1]['id'] not in popularity.popularity_for([r['id'] for r in rows], db)
    for change in [{'value': -1}, {'value': True}, {'source_url': 'https://map.naver.com.evil.test/x'},
                   {'checked_at': (date.today() + timedelta(days=1)).isoformat()}]:
        with pytest.raises(ValidationError): popularity.import_observations([{**good, **change}], db)


def test_instagram_branch_post_counts_can_be_imported_without_using_brand_followers(db):
    rows = seed(db)
    entry = {**observation(rows[0], 250), 'metric': 'instagram_place_posts',
             'source_url': 'https://www.instagram.com/explore/locations/123/example/'}
    popularity.import_observations([entry], db)
    signal = recommend()['recommendations'].items[0].discovery.popularity[0]
    assert signal.label == '인스타그램 장소 게시물' and signal.value == 250
    with pytest.raises(ValidationError):
        popularity.import_observations([{**entry, 'metric': 'instagram_followers'}], db)


def test_naver_review_order_matches_only_unique_exact_branches_and_keeps_rank(db, monkeypatch):
    rows = seed(db)
    def item(place, **extra):
        return dict(title='<b>' + place['name'] + '</b>', category='카페,디저트',
                    mapx=str(round(place['lng'] * 1e7)), mapy=str(round(place['lat'] * 1e7)), **extra)
    payload = {'items': [{**item(rows[0]), 'title': 'Different branch'}, item(rows[1]),
                         {**item(rows[2]), 'mapx': 'not-a-coordinate'}]}
    signals = popularity.naver_observations(payload, '종로 카페', db)
    assert len(signals) == 1 and signals[0]['place_id'] == rows[1]['id'] and signals[0]['value'] == 2
    assert signals[0]['metric'] == 'naver_local_rank'
    assert parse_qs(urlsplit(signals[0]['source_url']).query)['sort'] == ['comment']
    popularity.import_observations(signals, db)
    assert popularity.popularity_for([rows[1]['id']], db, date.today() + timedelta(days=31)) == {}
    from pipeline.naver_local import NaverLocalClient
    calls = []
    monkeypatch.setenv('NAVER_CLIENT_ID', 'id')
    monkeypatch.setenv('NAVER_CLIENT_SECRET', 'secret')
    monkeypatch.setattr(NaverLocalClient, 'search', lambda self, query, sort: calls.append((query, sort)) or [])
    assert popularity.fetch_naver('종로 카페') == {'items': []} and calls == [('종로 카페', 'comment')]


def test_chain_wide_photos_are_not_presented_or_counted_as_branch_photos(db):
    rows = seed(db)
    with catalog.connect(db) as conn:
        conn.execute('UPDATE places SET tags=? WHERE id=?', (json.dumps({'wikidata': 'Q37158'}), rows[0]['id']))
    photo(rows[0], db, 'wikidata:P373', 'Category:Starbucks')
    assert photos.photos_for([rows[0]['id']], db) == {}
    assert photos.photo_counts_for([rows[0]['id']], db) == {}
    assert not photos.nearby_entity({'id': 'Q37158'}, rows[0])
    photo(rows[0], db)  # An explicit photo of this branch remains valid.
    assert photos.photo_counts_for([rows[0]['id']], db) == {rows[0]['id']: 1}
    assert len(photos.photos_for([rows[0]['id']], db)[rows[0]['id']]) == 1
