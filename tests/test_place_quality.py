import json
import sqlite3

import pytest
from fastapi import HTTPException

from api.catalog_bridge import find
from api.preview import PreviewIn, evaluate
from pipeline import place_catalog as catalog, place_quality as quality
from scripts.audit_place_quality import audit
from scripts.export_catalog import export


def element(n, name, **tags):
    return {"id": n, "type": "node", "lat": 37.5796, "lon": 126.977,
            "tags": {"name": name, **tags}}


@pytest.mark.parametrize("name,tags", [
    ("혼천의", {"historic": "monument"}),
    ("혼천의", {"tourism": "artwork"}),
    ("혼천의(복제품)", {"tourism": "attraction"}),
    ("측우기", {"historic": "monument"}),
    ("앙부일구", {"historic": "monument"}),
    ("세종대왕 동상", {"historic": "monument", "building": "yes"}),
    ("문인석", {"historic": "yes", "tourism": "artwork"}),
    ("함지그린 공원 운동기구", {"historic": "monument"}),
    ("서울둘레길8코스북한산6스탬프", {"amenity": "post_box", "tourism": "attraction"}),
    ("[Seoul Trail] Stamp Deck", {"tourism": "attraction"}),
    ("비석", {"historic": "archaeological_site"}),
    ("North American T-28A Trojan", {"historic": "aircraft;memorial"}),
    ("유림아파트", {"historic": "castle"}),
    ("이제현교수님댁", {"historic": "castle"}),
    ("빌레못동굴(미개방)", {"tourism": "attraction"}),
    ("조각 작품", {"tourism": "artwork", "artwork_type": "sculpture"}),
    ("종", {"historic": "monument"}),
    ("어느 기념물", {"historic": "memorial"}),
])
def test_individual_objects_cannot_be_imported_even_with_category_override(name, tags):
    raw = element(1, name, **tags)
    assert catalog.normalize(raw, "now") is None
    assert catalog.normalize(raw, "now", category_override="heritage") is None


@pytest.mark.parametrize("name,tags,expected", [
    ("경복궁", {"historic": "palace"}, "heritage"),
    ("숭례문", {"historic": "city_gate"}, "heritage"),
    ("종묘", {"historic": "yes", "tourism": "attraction"}, "heritage"),
    ("윤극영 가옥", {"historic": "monument"}, "heritage"),
    ("돈의문터", {"historic": "monument"}, "heritage"),
    ("부왕동암문", {"historic": "monument"}, "heritage"),
    ("올림픽공원 세계평화의문", {"historic": "monument", "building": "yes"}, "heritage"),
    ("부산근대역사관", {"historic": "memorial", "tourism": "museum"}, "museum"),
    ("근현대사기념관", {"historic": "monument"}, "museum"),
    ("윤동주기념관 (521)", {"historic": "monument"}, "museum"),
    ("대청공원", {"historic": "monument"}, "park"),
    ("혼천의", {"amenity": "cafe"}, "cafe"),
    ("해시계공원", {"leisure": "park"}, "park"),
    ("조각공원", {"leisure": "park", "tourism": "artwork"}, "park"),
    ("홍대벽화거리", {"tourism": "artwork"}, "attraction"),
    ("연주대", {"natural": "peak"}, "scenic"),
    ("코끼리바위", {"natural": "rock"}, "scenic"),
    ("나홀로나무", {"tourism": "attraction", "natural": "tree"}, "attraction"),
    ("청사포다릿돌전망대", {"tourism": "attraction"}, "attraction"),
    ("공근혜갤러리", {"tourism": "artwork"}, "gallery"),
    ("PKM Galeria de arte", {"tourism": "artwork"}, "gallery"),
])
def test_actual_venues_are_retained_and_classified(name, tags, expected):
    row = catalog.normalize(element(1, name, **tags), "now")
    assert row and row["category"] == expected


def test_reviewed_exceptions_are_scoped_to_source_and_name():
    for source, (name, kind, _) in quality.REVIEWED_SPACES.items():
        assert quality.corrected_category(name, {"tourism": "artwork"}, source) == kind
        assert quality.exclusion_reason(name, {"tourism": "artwork"}, source) is None
        assert quality.exclusion_reason("알 수 없는 조각 작품", {"tourism": "artwork"}, source)


def test_rental_only_cafe_is_excluded_without_affecting_same_name_elsewhere():
    source = 'https://www.openstreetmap.org/node/7237249685'
    assert quality.exclusion_reason('서울리즘', {'amenity': 'cafe'}, source) == 'rental_only_no_regular_visits'
    assert quality.exclusion_reason('서울리즘', {'amenity': 'cafe'}, 'https://www.openstreetmap.org/node/1') is None
    assert quality.exclusion_reason('다른 카페', {'amenity': 'cafe'}, source) is None


def test_ambiguous_monument_requires_review_and_not_any_historic_tag():
    assert quality.exclusion_reason("확인되지 않은 기념물 이름", {"historic": "monument"}) == "monument_needs_place_review"
    assert catalog.category({"historic": "no"}) is None
    assert catalog.category({"tourism": "artwork"}) is None


def seed_legacy(db):
    catalog.import_response("seoul", {"elements": [element(1, "카페", amenity="cafe"),
        element(2, "이전 수집 장소", amenity="cafe"), element(3, "수정 전 분류", amenity="cafe")]}, db)
    with catalog.connect(db) as conn:
        conn.execute("UPDATE places SET name=?,category=?,tags=? WHERE osm_id=2",
                     ("혼천의", "heritage", json.dumps({"historic": "monument"})))
        conn.execute("UPDATE places SET name=?,category=?,tags=? WHERE osm_id=3",
                     ("근현대사기념관", "heritage", json.dumps({"historic": "monument"})))
        return {r["osm_id"]: r["id"] for r in conn.execute("SELECT * FROM places")}


def test_legacy_objects_are_hidden_from_search_explicit_detail_and_auth(tmp_path, monkeypatch):
    db = tmp_path / "places.sqlite3"
    monkeypatch.setenv("PLACE_CATALOG_DB", str(db))
    ids = seed_legacy(db)
    # Protection works even before a legacy snapshot has been audited.
    assert ids[2] not in {r["id"] for r in catalog.search(37.5796, 126.977, 1000, ids=[ids[2]])}
    with pytest.raises(HTTPException) as error: find(ids[2])
    assert error.value.status_code == 404
    body = PreviewIn(visit_date="2026-10-10", place_ids=[ids[2]])
    result = evaluate(body)
    assert ids[2] not in result["places"]
    assert ids[2] not in {item.place_id for item in result["recommendations"].items}
    with catalog.connect(db) as conn: quality.reconcile(conn)
    assert ids[2] not in {r["id"] for r in catalog.search(37.5796, 126.977, 1000, ids=[ids[2]])}
    assert catalog.metadata()["count"] == 2
    assert find(ids[3])["category"] == "museum"


def test_audit_is_reversible_idempotent_and_export_keeps_exclusion(tmp_path, monkeypatch):
    db = tmp_path / "places.sqlite3"
    monkeypatch.setenv("PLACE_CATALOG_DB", str(db))
    ids = seed_legacy(db)
    report = tmp_path / "audit.json"
    dry = audit(path=db, report=report)
    assert dry["excluded"] == 1 and dry["reclassified"] == 1
    assert catalog.metadata()["count"] == 3
    result = audit(path=db, apply=True, report=report)
    assert result["remaining_active"] == 2 and result["backup"]
    with sqlite3.connect(result["backup"]) as original:
        assert original.execute("SELECT active FROM places WHERE id=?", (ids[2],)).fetchone()[0] == 1
    with catalog.connect(db) as conn:
        assert quality.reconcile(conn) == []
        assert conn.execute("SELECT count(*) FROM places").fetchone()[0] == 3
    destination = tmp_path / "published.sqlite3"
    export(destination)
    assert catalog.metadata(destination)["count"] == 2
    assert ids[2] not in {r["id"] for r in catalog.search(37.5796, 126.977, 1000, ids=[ids[2]], path=destination)}


def test_refresh_cannot_resurrect_objects_from_overlapping_regions(tmp_path):
    db = tmp_path / "places.sqlite3"
    ids = seed_legacy(db)
    with catalog.connect(db) as conn:
        conn.execute("INSERT INTO region_places VALUES (?,?)", ("busan", ids[2]))
    catalog.import_response("seoul", {"elements": [element(1, "카페", amenity="cafe"),
        element(2, "혼천의", historic="monument")]}, db)
    assert catalog.metadata(db)["count"] == 1
    with catalog.connect(db) as conn:
        assert conn.execute("SELECT active FROM places WHERE id=?", (ids[2],)).fetchone()[0] == 0
    # A real venue replacing the object can be imported normally with fresh facts.
    catalog.import_response("seoul", {"elements": [element(2, "천문박물관", tourism="museum")]}, db)
    assert catalog.search(37.5796, 126.977, 1000, path=db)[0]["category"] == "museum"
