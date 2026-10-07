import copy
from datetime import date
import json

import pytest
from fastapi.testclient import TestClient

from api.preview import app, evaluate, PreviewIn
from pipeline import place_catalog as catalog


def record(n=1, **tags):
    return {"type": "node", "id": n, "lat": 37.579, "lon": 126.977,
            "tags": {"name": f"테스트용 장소 {n}", "amenity": "cafe", **tags}}


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "places.sqlite3"
    monkeypatch.setenv("PLACE_CATALOG_DB", str(path))
    return path


def seed(db):
    return catalog.import_response("seoul", {"elements": [record(), record(2, amenity="", leisure="park"),
        record(3, amenity="", tourism="museum"), {**record(4), "lat": 35.1587, "lon": 129.1604}]}, db)


def test_upsert_preserves_ids_and_uses_received_values(db):
    assert seed(db) == 4
    first = catalog.search(37.5796, 126.977, 5000, path=db)
    assert len(first) == 3
    old = next(p for p in first if p["osm_id"] == 1)
    catalog.import_response("seoul", {"elements": [record(name="수정된 장소", **{"addr:full": "수집 주소"})]}, db)
    new = catalog.search(37.5796, 126.977, 5000, path=db)[0]
    assert new["id"] == old["id"] and new["name"] == "수정된 장소" and new["address"] == "수집 주소"
    assert new["source_url"] == "https://www.openstreetmap.org/node/1"
    assert catalog.metadata(db)["count"] == 1


def test_partial_and_empty_responses_never_replace_existing_db(db):
    seed(db)
    for raw in [{"remark": "runtime error", "elements": [record()]}, {"elements": []}, {}]:
        with pytest.raises(ValueError): catalog.import_response("seoul", raw, db)
        assert catalog.metadata(db)["count"] == 4


@pytest.mark.parametrize("patch", [{"lat": 0}, {"lon": float("nan")}, {"id": -1}, {"type": "other"}])
def test_invalid_coordinates_and_ids_filtered(patch):
    assert catalog.normalize({**record(), **patch}, "now") is None


def test_private_and_closed_places_and_personal_tags_are_not_imported():
    assert catalog.normalize(record(access="private"), "now") is None
    assert catalog.normalize(record(disused="yes"), "now") is None
    p = catalog.normalize(record(phone="private-number", contact="person", amenity="cafe"), "now")
    assert "private-number" not in p["tags"] and "person" not in p["tags"]


def test_no_database_means_error_not_sample_fallback(db):
    response = TestClient(app).post("/preview/evaluate", json={"visit_date": "2026-10-10"})
    assert response.status_code == 503 and "준비" in response.json()["title"]


def test_real_catalog_contract_does_not_invent_photographic_evidence(db):
    seed(db)
    body = PreviewIn(profile={"body_type": "natural", "mbti": "INFP"}, visit_date=date(2026, 10, 10), use_saju=True, element="water",
                     percents={"wood": 5, "fire": 15, "earth": 20, "metal": 25, "water": 35})
    result = evaluate(body)
    rec = result["recommendations"]
    assert rec.catalog.count == 4 and rec.catalog.provider == "openstreetmap"
    assert rec.items[0].spot_name == "공원·정원"
    assert all(i.practical_score is None and not i.scene_id and i.source.url for i in rec.items)
    assert rec.items[0].fit_score is None and rec.items[0].score == 0
    p = result["places"][rec.items[0].place_id]
    assert p.best_scene is None and p.open_on_visit_date is None and p.analysis_pending
    assert p.fit_score == rec.items[0].fit_score
    assert p.recommended_elements == rec.items[0].recommended_elements == ["wood"]
    assert p.element_profile and p.scoring.evaluated_weight == 0
    body.use_saju = False
    body.profile.body_type = "straight"
    body.profile.mbti = "ENTJ"
    assert evaluate(body)["recommendations"].items[0].spot_name == "박물관·미술관"


def test_bookmark_detail_outside_search_area_remains_accessible(db):
    seed(db)
    far = catalog.search(35.1587, 129.1604, 1000, path=db)[0]
    r = evaluate(PreviewIn(visit_date=date(2026, 10, 10), place_ids=[far["id"]]))
    assert far["id"] in r["places"]
    assert far["id"] not in [i.place_id for i in r["recommendations"].items]


def test_database_search_does_not_call_external_provider(db, monkeypatch):
    seed(db)
    def fail(*args): raise AssertionError("An app query must not call Overpass")
    monkeypatch.setattr(catalog, "fetch_region", fail)
    assert evaluate(PreviewIn(visit_date=date(2026, 10, 10)))["recommendations"].items


@pytest.mark.parametrize("profile,expected", [
    ({}, {"카페": None, "공원·정원": None, "박물관·미술관": None}),
    ({"pc_season": "summer_cool"}, {"카페": None, "공원·정원": None, "박물관·미술관": None}),
    ({"body_type": "wave"}, {"카페": 100, "공원·정원": 100, "박물관·미술관": 0}),
    ({"mbti": "INFP"}, {"카페": 0, "공원·정원": 100, "박물관·미술관": 0}),
    ({"body_type": "wave", "mbti": "INFP"}, {"카페": 60, "공원·정원": 100, "박물관·미술관": 0}),
    ({"body_type": "straight", "mbti": "INFP"}, {"카페": 0, "공원·정원": 40, "박물관·미술관": 60}),
])
def test_fit_score_uses_supplied_inputs_and_matches_detail(db, profile, expected):
    seed(db)
    result = evaluate(PreviewIn(profile=profile, visit_date="2026-10-10"))
    items = result["recommendations"].items
    # No observed photos in this fixture: never invent scores from category.
    assert all(i.fit_score is None for i in items)
    for item in items:
        detail = result["places"][item.place_id]
        assert detail.fit_score == item.fit_score
        assert detail.scoring == item.scoring
        assert item.scoring.score == item.fit_score
        scored = [m for m in item.scoring.metrics if m.status == 'scored']
        assert sum(m.points for m in scored) == (item.fit_score or 0)
        assert sum(m.maximum for m in scored) == (100 if scored else 0)
        pending = [m for m in item.scoring.metrics if m.status == 'pending']
        assert all(m.points is None for m in pending)
        assert item.recommended_elements == detail.recommended_elements == []
        if item.fit_score is not None:
            assert item.score == item.fit_score
    scores = [i.fit_score for i in items if i.fit_score is not None]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize("tags,expected", [
    ({"natural": "peak"}, "scenic"), ({"natural": "cave_entrance"}, "scenic"),
    ({"waterway": "waterfall"}, "scenic"), ({"tourism": "theme_park"}, "theme_park"),
    ({"amenity": "festival_grounds"}, "festival_site"), ({"landuse": "fairground"}, "festival_site"),
    ({"amenity": "theatre"}, "cultural_venue"), ({"amenity": "arts_centre"}, "cultural_venue"),
    ({"amenity": "conference_centre"}, "event_venue"), ({"amenity": "exhibition_centre"}, "event_venue"),
    ({"amenity": "events_venue"}, None),  # Generic event venues can be private wedding/banquet halls.
])
def test_travel_and_public_event_categories(tags, expected):
    assert catalog.category(tags) == expected


def test_supplemental_refresh_preserves_existing_and_full_refresh_cleans_membership(db):
    seed(db)
    cafe = next(p for p in catalog.search(37.5796, 126.977, 5000, path=db) if p['osm_id'] == 1)
    catalog.import_response('seoul', {'elements': [record(5, amenity='theatre')]}, db, scope='spaces')
    assert catalog.metadata(db)['count'] == 5
    assert catalog.metadata(db)['regions'] == ['seoul']
    catalog.import_response('seoul', {'elements': [record(6, amenity='festival_grounds')]}, db, scope='spaces')
    assert catalog.metadata(db)['count'] == 5
    with pytest.raises(ValueError):
        catalog.import_response('seoul', {'elements': [], 'remark': 'timeout'}, db, scope='spaces')
    assert catalog.metadata(db)['count'] == 5
    assert next(p for p in catalog.search(37.5796, 126.977, 5000, path=db) if p['osm_id'] == 1)['id'] == cafe['id']
    catalog.import_response('seoul', {'elements': [record()]}, db)
    assert catalog.metadata(db)['count'] == 1
    with catalog.connect(db) as conn:
        assert not conn.execute("SELECT 1 FROM imports WHERE region LIKE '%:spaces'").fetchone()


def test_group_filter_runs_before_limit_and_details_remain_accessible(db):
    records = [record(n) for n in range(1, 36)] + [record(36, amenity='theatre'),
        record(37, amenity='', natural='peak'), record(38, amenity='', tourism='theme_park')]
    catalog.import_response('seoul', {'elements': records}, db)
    request = dict(profile={'body_type': 'wave'}, visit_date='2026-10-10')
    all_items = evaluate(PreviewIn(**request))['recommendations'].items
    assert len(all_items) == 30 and all(i.place_group == 'cafe' for i in all_items)
    result = evaluate(PreviewIn(**request, place_group='festival', place_ids=[all_items[0].place_id]))
    rec = result['recommendations']
    assert rec.place_group == 'festival' and len(rec.items) == 1
    assert rec.items[0].place_group == 'festival' and rec.items[0].time_slot_label == '행사 일정 확인 필요'
    assert rec.catalog.group_counts == {'cafe': 35, 'travel': 2, 'festival': 1}
    assert all_items[0].place_id in result['places']
    detail = result['places'][rec.items[0].place_id]
    assert detail.place_group == 'festival' and detail.open_on_visit_date is None
    assert any('실제 행사 개최 여부' in note for note in detail.visit_notes)
    travel = evaluate(PreviewIn(**request, place_group='travel'))['recommendations'].items
    assert len(travel) == 2 and all(i.place_group == 'travel' for i in travel)
    assert all(i.hours is None and i.time_slot_label == '운영시간 · 지도에서 확인' for i in travel)
    saju = evaluate(PreviewIn(**request, place_group='festival', use_saju=True, element='wood',
                             percents={'wood': 0, 'fire': 25, 'earth': 25, 'metal': 25, 'water': 25}))
    assert not saju['recommendations'].items  # Do not invent an element for a venue to fill the list.


def test_empty_group_has_no_cafe_fallback_and_unknown_group_rejected(db):
    seed(db)
    client = TestClient(app)
    result = client.post('/preview/evaluate', json={'visit_date': '2026-10-10', 'place_group': 'festival'})
    assert result.status_code == 200 and result.json()['recommendations']['items'] == []
    assert client.post('/preview/evaluate', json={'visit_date': '2026-10-10', 'place_group': 'unknown'}).status_code == 422
