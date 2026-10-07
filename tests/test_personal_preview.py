from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api.preview import app, evaluate_sample as evaluate, PreviewIn
from api.services import daily_context

client = TestClient(app)
A = {"gender": "female", "birth_year": 1993, "height_cm": 168.5, "pc_season": "summer_cool",
     "pc_subtone": "light", "body_type": "wave", "mbti": "INFP"}
B = {"gender": "male", "birth_year": 1987, "height_cm": 181, "pc_season": "winter_cool",
     "pc_subtone": "deep", "body_type": "straight", "mbti": "ENTJ"}
PERCENTS = {"wood": 5, "fire": 15, "earth": 20, "metal": 25, "water": 35}


def result(profile=None, **kwargs):
    if kwargs.get("element"): kwargs.setdefault("percents", PERCENTS)
    return evaluate(PreviewIn(profile=profile or {}, visit_date=kwargs.pop("visit_date", date(2026, 10, 10)), **kwargs))


def test_real_profile_values_not_fixture_values():
    p = client.post("/preview/profile", json=A).json()
    assert all(p[k] == v for k, v in A.items())
    assert p["height_band"] == "tall"
    card = result(A)["card"]
    assert "168.5cm" in card.subtitle and "162cm" not in card.subtitle
    assert "INFP" in card.subtitle and card.lucky is None
    assert "ENTJ" in result(B)["card"].subtitle


def test_different_inputs_change_scores_reasons_and_ranking():
    a, b = result(A)["recommendations"], result(B)["recommendations"]
    assert a.items[0].place_id != b.items[0].place_id
    assert a.items[0].reasons != b.items[0].reasons
    assert a.items[0].score != b.items[0].score


def test_empty_inputs_never_inherit_example_traits():
    r = result()
    assert r["card"].best_light == []
    assert all(i.score == 0 and i.reasons == [] for i in r["recommendations"].items)
    assert len(r["recommendations"].missing_inputs) == 4


def test_actual_birth_dates_produce_different_pillars_and_percentages():
    a = client.post("/preview/saju", json={"birth_date": "1993-08-21", "birth_time": "09:30", "consent": True})
    b = client.post("/preview/saju", json={"birth_date": "1987-12-09", "birth_time": "23:00", "consent": True})
    assert a.status_code == b.status_code == 200
    assert a.json()["pillars"] != b.json()["pillars"]
    assert a.json()["percents"] != b.json()["percents"]
    assert a.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("birth", ["2026-02-31", "1899-01-01", "2099-01-01"])
def test_invalid_birth_is_rejected_without_echoing_private_input(birth):
    r = client.post("/preview/saju", json={"birth_date": birth, "consent": True})
    assert r.status_code == 422 and birth not in r.text


def test_lunar_date_and_unknown_time_use_real_calculator():
    lunar = client.post("/preview/saju", json={"birth_date": "1990-02-30", "calendar": "lunar", "consent": True})
    assert lunar.status_code == 200
    assert not lunar.json()["has_birth_time"] and "hour" not in lunar.json()["pillars"]
    no_consent = client.post("/preview/saju", json={"birth_date": "1993-08-21", "consent": False})
    assert no_consent.status_code == 400


def test_daily_is_opt_in_and_requires_personal_element():
    assert result(A, element="wood")["recommendations"].daily is None
    assert result(A, use_saju=True)["recommendations"].daily is None
    with_day = result(A, element="wood", use_saju=True)["recommendations"]
    base = result(A)["recommendations"]
    assert with_day.daily.personal_element == "wood"
    assert with_day.daily.deficient_elements == ["wood"]
    base_scores = {i.place_id: i.practical_score for i in base.items}
    assert all(i.practical_score == base_scores[i.place_id] for i in with_day.items)
    assert [i.score for i in with_day.items] != [i.score for i in base.items]
    assert all("일진" not in r.label and "나의 목" not in r.label for i in base.items for r in i.reasons)


def test_day_changes_with_selected_date_and_repeats_after_sixty_days():
    d = date(2026, 10, 10)
    first = daily_context(d, "wood", True, PERCENTS)
    assert first["pillar"] != daily_context(d + timedelta(days=1), "wood", True, PERCENTS)["pillar"]
    assert first["pillar"] == daily_context(d + timedelta(days=60), "wood", True, PERCENTS)["pillar"]
    a = result(A, element="wood", use_saju=True)
    b = result(A, element="wood", use_saju=True, visit_date=d + timedelta(days=3))
    assert a["recommendations"].daily.day_element != b["recommendations"].daily.day_element
    assert [i.score for i in a["recommendations"].items] != [i.score for i in b["recommendations"].items]


def test_list_detail_share_scores_and_filters_are_applied():
    r = result(A, element="fire", use_saju=True)
    for item in r["recommendations"].items:
        detail = r["places"][item.place_id].best_scene
        assert detail.score == item.score and detail.reasons == item.reasons
    assert result(A, lat=35.1587, lng=129.1604)["recommendations"].items == []
    assert result(A, time_slot="morning")["recommendations"].items == []
    monday = result(A, visit_date=date(2026, 10, 12))["recommendations"]
    assert all(i.place_name != "창경궁 대온실" for i in monday.items)
