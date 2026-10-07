"""사주 계산기 테스트."""
import os
import sys
from datetime import date, datetime, time, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from saju.astro import term_time                                   # noqa: E402
from saju.calculator import ForcetellerStyleCalculator, lunar_to_solar   # noqa: E402
from saju.elements import weigh                                    # noqa: E402
from saju.pillars import FourPillars, Pillar, day_pillar, four_pillars, to_utc  # noqa: E402

KST = timezone(timedelta(hours=9))
S = "甲乙丙丁戊己庚辛壬癸"
B = "子丑寅卯辰巳午未申酉戌亥"


def P(text: str) -> Pillar:
    return Pillar(S.index(text[0]), B.index(text[1]))


def chart(y, m, d, h=None) -> FourPillars:
    return FourPillars(P(y), P(m), P(d), P(h) if h else None, datetime(2000, 1, 1))


# --- 절기 · 일진 ---------------------------------------------------------------
@pytest.mark.parametrize("year, deg, expected", [
    (2025, 315, "2025-02-03 23:10"),   # 입춘
    (2026, 315, "2026-02-04 05:02"),
    (2025, 270, "2025-12-22 00:03"),   # 동지
])
def test_solar_terms_within_ten_minutes(year, deg, expected):
    got = term_time(year, deg).astimezone(KST)
    exp = datetime.strptime(expected, "%Y-%m-%d %H:%M").replace(tzinfo=KST)
    assert abs((got - exp).total_seconds()) <= 600


def test_day_pillar_anchors():
    assert day_pillar(date(2000, 1, 1)).hanja == "戊午"
    assert day_pillar(date(1900, 1, 1)).hanja == "甲戌"


def test_four_pillars_known_chart():
    p = four_pillars(date(1998, 5, 14), time(14, 30))
    assert [x.hanja for x in (p.year, p.month, p.day, p.hour)] == ["戊寅", "丁巳", "辛酉", "乙未"]


def test_year_changes_at_ipchun_not_new_year():
    assert four_pillars(date(2025, 2, 3), time(12, 0)).year.hanja == "甲辰"   # 입춘(2/3 23:10) 전
    assert four_pillars(date(2025, 2, 4), time(12, 0)).year.hanja == "乙巳"


def test_solar_time_correction_moves_midnight_to_previous_day():
    p = four_pillars(date(2000, 1, 1), time(0, 0))
    assert p.day.hanja == "丁巳" and p.hour.branch == 0                       # 12/31 23:30 子시
    p2 = four_pillars(date(2000, 1, 1), time(0, 0), late_zi_next_day=True)
    assert p2.day.hanja == "戊午"


def test_no_birth_time_gives_three_pillars():
    p = four_pillars(date(1990, 10, 20), None)
    assert p.hour is None and p.month.hanja == "丙戌"


def test_korean_time_history():
    assert to_utc(datetime(1988, 6, 1, 12, 0)) == datetime(1988, 6, 1, 2, 0, tzinfo=timezone.utc)      # 서머타임
    assert to_utc(datetime(1960, 1, 1, 12, 0)) == datetime(1960, 1, 1, 3, 30, tzinfo=timezone.utc)     # UTC+8:30
    assert to_utc(datetime(2000, 1, 1, 12, 0)) == datetime(2000, 1, 1, 3, 0, tzinfo=timezone.utc)


def test_lunar_input():
    assert lunar_to_solar(date(1998, 3, 18)) == date(1998, 4, 14)
    r = ForcetellerStyleCalculator().calculate(date(1998, 3, 18), time(10, 0), calendar="lunar")
    assert r.pillars.year.hanja == "戊寅"


# --- 오행 가중치: 포스텔러 공개 역산값 재현 (조후·궁성 보정, 합 보정 없음) --------------------
def test_matches_forceteller_chart_a():
    r = weigh(chart("戊寅", "己戌", "辛卯", "戊寅"), harmony=False, climate=True)
    assert r.percents == {"wood": 31.8, "fire": 0.0, "earth": 40.9, "metal": 9.1, "water": 18.2}
    assert r.dominant == "earth"


def test_matches_forceteller_chart_b():
    r = weigh(chart("壬寅", "丁未", "癸丑", "丙寅"), harmony=False, climate=True)
    assert r.percents == {"wood": 18.2, "fire": 50.0, "earth": 13.6, "metal": 0.0, "water": 18.2}
    assert r.dominant == "fire"


def test_position_weights_sum():
    r = weigh(chart("甲子", "丙寅", "戊辰", "庚午"), harmony=False, climate=False)
    assert round(sum(r.scores.values()), 6) == 22
    r6 = weigh(chart("甲子", "丙寅", "戊辰"), harmony=False, climate=False)
    assert round(sum(r6.scores.values()), 6) == 18


# --- 합충 보정 (표준 규칙) ----------------------------------------------------
def test_stem_combination_transforms_both():
    # 월간 甲 + 일간 己 → 土 (일간이 포함된 합도 합화)
    off = weigh(chart("壬子", "甲寅", "己酉", "丙寅"), harmony=False, climate=False)
    on = weigh(chart("壬子", "甲寅", "己酉", "丙寅"), harmony=True, climate=False)
    assert on.scores["earth"] == off.scores["earth"] + 2 and on.scores["wood"] == off.scores["wood"] - 2
    assert any("천간합" in n for n in on.corrections)


def test_triad_combination_and_clash_protection():
    # 申子辰 삼합 → 水. 子午충은 子가 합에 참여해서 발생하지 않음
    r = weigh(chart("庚申", "戊子", "甲辰", "丙午"), harmony=True, climate=False)
    assert any("삼합" in n for n in r.corrections) and not any("충" in n for n in r.corrections)
    assert r.scores["water"] == 2 + 7 + 3                        # 년지·월지·일지가 모두 水


def test_clash_halves_both():
    off = weigh(chart("庚子", "戊午", "丙寅", "戊寅"), harmony=False, climate=False)
    on = weigh(chart("庚子", "戊午", "丙寅", "戊寅"), harmony=True, climate=False)
    assert on.scores["water"] == off.scores["water"] - 1        # 년지 子 2 → 1
    assert on.scores["fire"] == off.scores["fire"] - 3.5        # 월지 午 7 → 3.5
    assert round(sum(on.scores.values()), 6) == 22 - 4.5


def test_climate_skipped_when_month_branch_combined():
    # 卯戌 육합(월지 戌 참여) → 조후 보정을 적용하지 않음
    r = weigh(chart("甲寅", "壬戌", "己卯", "甲子"), harmony=True, climate=True)
    assert not any("조후" in n for n in r.corrections)


def test_dominant_is_single_max():
    r = ForcetellerStyleCalculator().calculate(date(1990, 10, 20), None)
    assert r.dominant == max(r.elements.percents, key=r.elements.percents.get)
