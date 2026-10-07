from datetime import date

import pytest

from api.preview import PreviewIn, evaluate
from api.services import deficient_elements, daily_context, recommended_elements
from pipeline import place_catalog as catalog


@pytest.mark.parametrize("percents,expected", [
    ({"wood": 50, "fire": 20, "earth": 15, "metal": 10, "water": 5}, ["water"]),
    ({"wood": 0, "fire": 30, "earth": 30, "metal": 0, "water": 40}, ["wood", "metal"]),
    (dict.fromkeys(["wood", "fire", "earth", "metal", "water"], 20), []),
    (None, None), ({"wood": 20}, None),
    ({"wood": float("nan"), "fire": 20, "earth": 20, "metal": 20, "water": 20}, None),
    (dict.fromkeys(["wood", "fire", "earth", "metal", "water"], 0), None),
])
def test_lowest_percentages_and_ties(percents, expected):
    assert deficient_elements(percents) == expected


def test_dominant_alone_never_implies_a_deficit():
    assert daily_context(date(2026, 10, 10), "wood", True) is None


def test_recommendation_labels_only_include_elements_present_at_place():
    daily = {"deficient_elements": ["fire", "earth"], "day_element": "water"}
    assert recommended_elements({"earth"}, daily) == ["earth"]
    assert recommended_elements({"earth", "water"}, daily) == ["earth", "water"]
    assert recommended_elements({"metal"}, daily) == []
    assert recommended_elements({"earth"}, None) == []
    daily["day_element"] = "earth"
    assert recommended_elements({"earth"}, daily) == ["earth"]


def test_real_places_filter_for_lacking_element_and_leave_base_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("PLACE_CATALOG_DB", str(tmp_path / "catalog.sqlite3"))
    tags = [{"leisure": "park"}, {"natural": "beach"}, {"amenity": "cafe"}, {"tourism": "museum", "material": "steel"}]
    catalog.import_response("seoul", {"elements": [{"id": i + 1, "type": "node", "lat": 37.579, "lon": 126.977,
        "tags": {"name": f"Place {i}", **t}} for i, t in enumerate(tags)]})
    body = PreviewIn(visit_date="2026-10-10", element="wood", profile={"body_type": "natural", "mbti": "INFP"},
                     percents={"wood": 50, "fire": 20, "earth": 15, "metal": 10, "water": 5})
    base = evaluate(body)["recommendations"]
    assert len(base.items) == 4 and base.daily is None
    body.use_saju = True
    extra = evaluate(body)["recommendations"]
    assert extra.daily.deficient_elements == ["water"]
    assert [p.spot_name for p in extra.items] == ["물가·해변"]
    assert any("부족한 수" in r.label for r in extra.items[0].reasons)
    body.percents = {"wood": 0, "fire": 30, "earth": 30, "metal": 0, "water": 40}
    tied = evaluate(body)["recommendations"]
    assert {p.spot_name for p in tied.items} == {"공원·정원", "박물관·미술관"}
    assert tied.daily.deficient_elements == ["wood", "metal"]
    body.percents = {"wood": 50, "fire": 0, "earth": 20, "metal": 20, "water": 10}
    assert evaluate(body)["recommendations"].items == []  # Unknown fire evidence is not invented.
    body.use_saju = False
    assert evaluate(body)["recommendations"] == base
