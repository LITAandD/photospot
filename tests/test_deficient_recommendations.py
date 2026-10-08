from datetime import date

import pytest

from api.preview import PreviewIn, evaluate
from api.services import deficient_elements, daily_context, recommended_elements, element_priorities, saju_place_match
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
    water_alternative = evaluate(body)["recommendations"].items
    assert [p.spot_name for p in water_alternative] == ["물가·해변"]
    assert all('fire' not in p.recommended_elements for p in water_alternative)  # Never invent fire evidence.
    body.use_saju = False
    assert evaluate(body)["recommendations"] == base


def test_day_relations_and_rounding_preserve_valid_candidates():
    percents = dict.fromkeys(['wood', 'fire', 'earth', 'metal', 'water'], 20)
    priorities = {p['element']: p for p in element_priorities(percents, 'wood')}
    assert {e: p['day_points'] for e, p in priorities.items()} == {'wood': 24, 'fire': 30, 'earth': 0, 'metal': 6, 'water': 18}
    assert all(p['personal_points'] == 0 for p in priorities.values())
    balanced = daily_context(date(2026, 10, 7), 'wood', True, percents)
    assert balanced['target_elements'] == ['fire', 'wood']
    rounded = {'wood': 20.1, 'fire': 20.1, 'earth': 20.2, 'metal': 20.2, 'water': 20.2}
    assert daily_context(date(2026, 10, 7), 'water', True, rounded)['target_elements']


def test_combined_score_breaks_equal_coverage_and_fit_ties_before_photo_priority(tmp_path, monkeypatch):
    from api import catalog_recommendations as recommendations
    monkeypatch.setenv('PLACE_CATALOG_DB', str(tmp_path / 'combined.sqlite3'))
    catalog.import_response('seoul', {'elements': [
        {'id': 901, 'type': 'node', 'lat': 37.5796, 'lon': 126.977, 'tags': {'name': 'Wood park', 'leisure': 'park'}},
        {'id': 902, 'type': 'node', 'lat': 37.5797, 'lon': 126.977, 'tags': {'name': 'Metal museum', 'tourism': 'museum', 'material': 'steel'}},
        {'id': 903, 'type': 'node', 'lat': 37.5798, 'lon': 126.977, 'tags': {'name': 'Unknown cafe', 'amenity': 'cafe'}},
    ]})
    rows = catalog.search(37.5796, 126.977, 5000)
    metal_id = next(p['id'] for p in rows if p['name'] == 'Metal museum')
    monkeypatch.setattr(recommendations, 'photo_counts_for', lambda ids: {metal_id: 10})
    body = PreviewIn(visit_date='2026-10-07', element='water', use_saju=True,
                     percents={'wood': 0, 'fire': 30, 'earth': 30, 'metal': 0, 'water': 40})
    first = evaluate(body)
    assert [p.place_name for p in first['recommendations'].items] == ['Wood park', 'Metal museum']
    assert [p.saju_match.score for p in first['recommendations'].items] == [94, 76]
    body.visit_date = date(2026, 10, 11)
    second = evaluate(body)
    assert [p.place_name for p in second['recommendations'].items] == ['Metal museum', 'Wood park']
    assert [p.saju_match.score for p in second['recommendations'].items] == [100, 76]
    for result in (first, second):
        for item in result['recommendations'].items:
            assert item.saju_match == result['places'][item.place_id].saju_match
            assert item.score == 0 and item.fit_score is None  # No invented photographic score.
            assert item.saju_match.score == round(item.saju_match.personal_points + item.saju_match.day_points, 1)

    # A lower saju score cannot outrank a place with more evaluated basic metrics.
    wood_id = next(p['id'] for p in rows if p['name'] == 'Wood park')
    monkeypatch.setattr(recommendations, 'photo_counts_for', lambda ids: {metal_id: 10, wood_id: 1})
    monkeypatch.setattr(recommendations, 'evidence_for', lambda ids: {
        wood_id: {'attributes': {'color_temp': 'warm', 'form': 'curved'}, 'method': 'test reviewed photo'},
        metal_id: {'attributes': {'color_temp': 'cool'}, 'method': 'test reviewed photo'},
    })
    body.profile = body.profile.model_copy(update={'pc_season': 'winter_cool', 'body_type': 'natural'})
    covered = evaluate(body)['recommendations'].items
    assert [p.place_name for p in covered] == ['Wood park', 'Metal museum']
    assert [p.fit_score for p in covered] == [0, 30.4]
    assert [p.saju_match.score for p in covered] == [76, 100]

    # With equal counts, basic fit still precedes saju, photo count and distance.
    monkeypatch.setattr(recommendations, 'evidence_for', lambda ids: {
        wood_id: {'attributes': {'color_temp': 'cool'}, 'method': 'test reviewed photo'},
        metal_id: {'attributes': {'color_temp': 'warm'}, 'method': 'test reviewed photo'},
    })
    fitted = evaluate(body)['recommendations'].items
    assert [p.place_name for p in fitted] == ['Wood park', 'Metal museum']
    assert [p.fit_score for p in fitted] == [30.4, 0]
    body.use_saju = False
    assert all(p.saju_match is None and p.recommended_elements == [] for p in evaluate(body)['recommendations'].items)


def test_only_supported_targets_receive_a_single_combined_score():
    context = daily_context(date(2026, 10, 7), 'water', True,
                            {'wood': 0, 'fire': 30, 'earth': 30, 'metal': 0, 'water': 40})
    assert saju_place_match({'wood', 'metal'}, context)['score'] == 94
    assert saju_place_match(set(), context) is None
    assert saju_place_match({'water'}, context) is None
    assert recommended_elements({'wood', 'metal', 'water'}, context) == ['wood', 'metal']
