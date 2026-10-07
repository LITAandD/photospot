from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.preview import app
from api.schemas import SajuIn
from saju.calculator import BIRTH_BRANCHES, ForcetellerStyleCalculator
from saju.pillars import day_pillar


def test_eight_digit_birth_date_normalizes_before_date_validation():
    b = SajuIn(birth_date="19930821", consent=True)
    assert b.birth_date == "1993-08-21"
    with pytest.raises(ValidationError): SajuIn(birth_date="00000000", consent=True)
    with pytest.raises(ValidationError): SajuIn(birth_date="20260231", consent=True)
    assert SajuIn(birth_date="19900230", calendar="lunar", consent=True).birth_date == "1990-02-30"


@pytest.mark.parametrize("branch", BIRTH_BRANCHES)
def test_selected_hour_branch_is_preserved_including_zi_and_dst(branch):
    calc = ForcetellerStyleCalculator()
    # During Korea's historic DST, exact civil-time correction must not remap an explicit branch.
    for birth in [date(1993, 8, 21), date(1988, 7, 1)]:
        r = calc.calculate(birth, None, birth_hour_branch=branch)
        assert r.pillars.hour.branch == BIRTH_BRANCHES.index(branch)
        assert r.pillars.day == day_pillar(birth)


def test_unknown_and_conflicting_time_inputs():
    c = TestClient(app)
    a = c.post("/preview/saju", json={"birth_date": "19930821", "birth_hour_branch": "zi", "consent": True})
    assert a.status_code == 200 and a.json()["pillars"]["hour"]["hangul"].endswith("자")
    assert a.json()["has_birth_time"]
    b = c.post("/preview/saju", json={"birth_date": "19930821", "consent": True})
    assert b.status_code == 200 and not b.json()["has_birth_time"] and "hour" not in b.json()["pillars"]
    bad = c.post("/preview/saju", json={"birth_date": "19930821", "birth_time": "14:30", "birth_hour_branch": "zi", "consent": True})
    assert bad.status_code == 422
