from datetime import date
import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from api.catalog_scoring import explanation
from api.scoring_cache import clear
from pipeline import catalog_visuals as visuals, catalog_classifications as classifications
from pipeline.catalog_mbti import import_records, descriptions_for, space_nature
from tests.test_mbti_evidence import places, description  # noqa: F401 (shared fixture)
from tests.test_photo_likes import venue  # noqa: F401 (shared fixture)


def test_data_coverage_is_independent_of_profile_and_zero_is_evaluated():
    evidence = {'attributes': {'color_temp': 'warm'}}
    empty = explanation({}, evidence)
    mismatch = explanation({'pc_season': 'winter_cool'}, evidence)
    assert empty['score'] is None and empty['preference_score'] is None
    assert empty['evidence_ready_count'] == mismatch['evidence_ready_count'] == 1
    assert mismatch['metrics'][0]['status'] == 'scored' and mismatch['metrics'][0]['points'] == 0
    assert mismatch['score'] == mismatch['preference_score'] == 0
    pending = explanation({'pc_season': 'winter_cool'}, None, photo_status='no_photo')
    assert pending['score'] is None and pending['metrics'][0]['evidence_status'] == 'no_photo'


def test_sparse_denominator_requires_profile_as_well_as_data():
    records = [dict(excerpt='테마 공간', source_url='https://example.org/space', label='Fixture', checked_at='2026-11-13')]
    evidence = {'attributes': {'form': 'curved'}}
    body = explanation({'body_type': 'wave'}, evidence, descriptions=records)
    both = explanation({'body_type': 'wave', 'mbti': 'ENTJ'}, evidence, descriptions=records)
    assert body['total_weight'] == 80 and both['total_weight'] == 90
    assert body['evidence_ready_count'] == both['evidence_ready_count'] == 2
    assert body['score'] == 37.5 and body['preference_score'] == 100
    assert both['score'] == 44.4 and both['preference_score'] == 100


def test_cover_url_and_source_must_both_match_and_rejected_review_stays_pending(tmp_path, monkeypatch):
    path = tmp_path/'catalog.sqlite3'
    photo = {'url': 'https://upload.wikimedia.org/A.jpg', 'source_url': 'https://commons.wikimedia.org/wiki/File:A.jpg'}
    visuals.store('a', photo, {'color_temp': 'warm', 'form': 'curved'}, 'photo-geometry-v1', path)
    diag = {}
    found = visuals.evidence_for(['a','empty','new'], path, selected_photos={'a':[photo], 'new':[photo]}, diagnostics=diag)
    assert diag == {'a': 'ready', 'empty': 'no_photo', 'new': 'analysis_pending'}
    assert 'form' not in found['a']['attributes']  # automatic candidates never approved
    for changed in ({**photo, 'url': photo['url']+'?new=1'}, {**photo, 'source_url': photo['source_url']+'2'}):
        assert not visuals.evidence_for(['a'], path, selected_photos={'a':[changed]}, diagnostics=diag)
        assert diag['a'] == 'cover_mismatch'
    monkeypatch.setitem(visuals.REVIEWS, 'a', {'photo_url': photo['url'], 'source_url': photo['source_url'], 'scene_usable': False})
    assert not visuals.evidence_for(['a'], path, selected_photos={'a':[photo]}, diagnostics=diag)
    assert diag['a'] == 'review_required'


def test_official_description_same_day_change_invalidates_cache(places):
    p = places[0]
    row = {**description(p, 'A concept courtyard'), 'provider': 'tourism',
           'source_url': 'https://english.visitkorea.or.kr/svc/whereToGo/fixture'}
    import_records([row])
    def points():
        return explanation({'mbti': 'ENTJ'}, None, p, descriptions=descriptions_for([p['id']])[p['id']])['metrics'][5]['points']
    assert points() == 10
    import_records([{**row, 'excerpt': 'Detailed walls without a concept'}])
    assert points() is None


def test_manual_classification_requires_exact_branch_and_review_date(places, monkeypatch):
    p = places[0]
    row = {**description(p), 'source_url': 'https://www.visitbusan.net/kr/fixture', 'value': 'nature', 'rationale': 'Fixture verified garden'}
    monkeypatch.setattr(classifications, 'records', lambda: {p['id']: row})
    monkeypatch.setattr(classifications, 'today', lambda: date(2026, 11, 13))
    assert space_nature(p)[0] == 'nature'
    for update in ({'place_name': 'Other branch'}, {'lat': 0}, {'checked_at': '2027-01-01'},
                   {'source_url': 'https://www.visitbusan.net.evil.test/page'}):
        monkeypatch.setattr(classifications, 'records', lambda update=update: {p['id']: {**row, **update}})
        assert space_nature(p)[0] == 'architecture'  # falls back to explicitly labelled map inference
    clear()


def test_unicode_photo_transport_preserves_identity_and_host_check(tmp_path, monkeypatch):
    import urllib.request
    import pytest
    image = BytesIO()
    Image.new('RGB', (100, 100), 'white').save(image, format='JPEG')
    seen = []
    class Opener:
        def open(self, request, timeout):
            seen.append(request.full_url)
            return BytesIO(image.getvalue())
    monkeypatch.setattr(visuals.catalog, 'ROOT', tmp_path)
    monkeypatch.setattr(urllib.request, 'build_opener', lambda *args: Opener())
    assert visuals.read_photo('https://postfiles.pstatic.net/카페%20사진.jpg?type=w580')
    assert '%EC%B9%B4%ED%8E%98%20' in seen[0] and '%2520' not in seen[0]
    with pytest.raises(ValueError): visuals.read_photo('https://evil.test/카페.jpg')
    assert len(seen) == 1


def test_refresh_rejects_old_cover_even_if_it_is_still_in_gallery(tmp_path, monkeypatch):
    from scripts import refresh_photo_evidence as refresh
    current = {'url': 'https://upload.wikimedia.org/new.jpg', 'source_url': 'https://commons.wikimedia.org/wiki/File:New.jpg', 'license_url': 'https://creativecommons.org/licenses/by/4.0/'}
    old = {**current, 'url': 'https://upload.wikimedia.org/old.jpg'}
    monkeypatch.setattr(refresh, 'photos_for', lambda ids: {'a': [current, old]})
    monkeypatch.setattr(refresh, 'read_photo', lambda url: (_ for _ in ()).throw(AssertionError('must not download stale cover')))
    result = refresh.refresh({'priority': {}, 'places': [{'id':'a', 'name':'A', 'cover':old, 'photo_status':'cover_mismatch'}]}, tmp_path/'report.json')
    assert result[0]['status'] == 'ineligible_or_stale'


def test_checked_in_analysis_manifest_has_image_identity_and_no_auto_form():
    rows = json.loads((Path(__file__).resolve().parents[1]/'pipeline/data/photo_analysis_manifest.json').read_text(encoding='utf-8'))
    from pipeline.photo_identity import photo_id
    for row in rows:
        assert row['photo_id'] == photo_id({'url': row['photo_url'], 'source_url': row['source_url'], 'original_url': row['original_url']})
        assert len(row['image_sha256']) == 64 and row['license_url'].startswith('https://')
        assert set(row['attributes']) == {'color_temp','brightness','saturation'}
        assert row['geometry'].get('review_required', True)


def test_visitor_pilot_reconciles_existing_annual_without_activating_new_scores():
    directory = Path(__file__).resolve().parents[1]/'pipeline/data'
    pilot = json.loads((directory/'visitor_pilot_gyeongbokgung.json').read_text(encoding='utf-8'))
    annual = next(r for r in json.loads((directory/'visitors_2025.json').read_text(encoding='utf-8')) if r['place_id'] == pilot['place_id'])
    assert sum(pilot['monthly_total']) == pilot['domestic_total'] + pilot['foreign_total'] == annual['visitors']
    assert len(pilot['monthly_total']) == 12 and annual['unit_id'] == pilot['unit_id']
    assert not pilot['new_scoring_enabled'] and not pilot['new_monthly_import_enabled']


def test_audit_rank_comparisons_cannot_read_a_different_live_snapshot(venue, monkeypatch):
    from api import photo_likes
    from scripts.audit_recommendation_evidence import audit
    def forbidden(*args, **kwargs):
        raise AssertionError('audit must use the supplied snapshot, not call the live store')
    monkeypatch.setattr(photo_likes, 'snapshot', forbidden)
    monkeypatch.setattr(photo_likes, 'evidence_for', forbidden)
    result = audit({'votes': [], 'evidence': []})
    assert result['photo_places'] == 1 and result['exact_photo_evidence'] == 1
    assert len(result['comparisons']) == 12
    assert photo_likes.snapshot is forbidden  # no process-wide override survives the audit
