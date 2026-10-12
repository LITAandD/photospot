from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api import preview
from api.preview import app, PreviewIn
from api.rate_limit import SlidingWindow
from api.services import daily_context

client = TestClient(app)
A = {"gender": "female", "birth_year": 1993, "height_cm": 168.5, "pc_season": "summer_cool",
     "pc_subtone": "light", "body_type": "wave", "mbti": "INFP"}
PERCENTS = {"wood": 5, "fire": 15, "earth": 20, "metal": 25, "water": 35}


def test_real_profile_values_are_echoed_with_derived_height_band():
    p = client.post("/preview/profile", json=A).json()
    assert all(p[k] == v for k, v in A.items())
    assert p["height_band"] == "tall"


def test_public_preview_has_no_plus_filters_and_ignores_old_client_keys():
    body = PreviewIn.model_validate({"visit_date": "2026-10-10", "photo_only": True, "min_fit": 90, "unknown": 1})
    assert not hasattr(body, "photo_only") and not hasattr(body, "min_fit")
    assert "photo_only" not in PreviewIn.model_fields and "min_fit" not in PreviewIn.model_fields


@pytest.mark.parametrize("extra", [{"place_ids": [str(i) for i in range(101)]}, {"radius_m": 50001},
                                   {"place_ids": ["x" * 65]}, {"limit": 51}])
def test_public_preview_bounds_requested_work(extra):
    r = client.post("/preview/evaluate", json={"visit_date": "2026-10-10", **extra})
    assert r.status_code == 422


def test_public_preview_accepts_every_radius_the_web_app_offers():
    for radius in [1000, 3000, 5000, 10000, 30000, 50000]:
        PreviewIn(visit_date=date(2026, 10, 10), radius_m=radius)
    PreviewIn(visit_date=date(2026, 10, 10), place_ids=[str(i) for i in range(100)])


def test_preview_is_rate_limited_per_client_ip(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(preview, "rate_limits", [("/preview/", SlidingWindow(2, clock=lambda: now[0]))])
    ok = {"birth_date": "1993-08-21", "consent": True}
    assert [client.post("/preview/saju", json=ok).status_code for _ in range(2)] == [200, 200]
    limited = client.post("/preview/saju", json=ok)
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) == 60
    assert client.get("/health").status_code == 200                       # Only /preview/* is limited.
    now[0] = 60.5
    assert client.post("/preview/saju", json=ok).status_code == 200
    monkeypatch.setattr(preview, "rate_limits", [("/preview/", SlidingWindow(0))])
    assert all(client.post("/preview/profile", json=A).status_code == 200 for _ in range(5))


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


def test_day_changes_with_selected_date_and_repeats_after_sixty_days():
    d = date(2026, 10, 10)
    first = daily_context(d, "wood", True, PERCENTS)
    assert first["pillar"] != daily_context(d + timedelta(days=1), "wood", True, PERCENTS)["pillar"]
    assert first["pillar"] == daily_context(d + timedelta(days=60), "wood", True, PERCENTS)["pillar"]
    assert first["day_element"] != daily_context(d + timedelta(days=3), "wood", True, PERCENTS)["day_element"]
