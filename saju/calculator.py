"""API에서 쓰는 사주 오행 계산기."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from .elements import ElementResult, weigh
from .pillars import FourPillars, Pillar, day_pillar, four_pillars

BIRTH_BRANCHES = ["zi", "chou", "yin", "mao", "chen", "si", "wu", "wei", "shen", "you", "xu", "hai"]


@dataclass
class SajuResult:
    pillars: FourPillars
    elements: ElementResult

    @property
    def dominant(self) -> str:
        return self.elements.dominant


def lunar_to_solar(d: date | str, leap_month: bool = False) -> date:
    from korean_lunar_calendar import KoreanLunarCalendar
    cal = KoreanLunarCalendar()
    year, month, day = (map(int, d.split("-")) if isinstance(d, str) else (d.year, d.month, d.day))
    if not cal.setLunarDate(year, month, day, leap_month) or cal.isIntercalation != leap_month:
        raise ValueError("음력 날짜가 올바르지 않아요")
    return date.fromisoformat(cal.SolarIsoFormat())


class ForcetellerStyleCalculator:
    """포스텔러 방식(궁성·조후 보정) + 표준 합충 보정. 가장 많은 오행 하나를 dominant로 준다."""

    def __init__(self, harmony: bool = True, climate: bool = True, longitude: float = 127.5,
                 late_zi_next_day: bool = False):
        self.harmony, self.climate = harmony, climate
        self.longitude, self.late_zi_next_day = longitude, late_zi_next_day

    def calculate(self, birth_date: date | str, birth_time: time | None, calendar: str = "solar",
                  leap_month: bool = False, birth_hour_branch: str | None = None) -> SajuResult:
        if calendar == "lunar":
            birth_date = lunar_to_solar(birth_date, leap_month)
        elif isinstance(birth_date, str):
            birth_date = date.fromisoformat(birth_date)
        if birth_hour_branch is not None:
            if birth_time is not None or birth_hour_branch not in BIRTH_BRANCHES:
                raise ValueError("태어난 시각과 12지시 중 하나만 올바르게 선택해 주세요")
            branch = BIRTH_BRANCHES.index(birth_hour_branch)
            # An explicit branch is not an exact civil time. Use the interval centre
            # for solar-term year/month boundaries, keep the entered day's pillar,
            # and assign the chosen branch directly (no second solar-time shift).
            reference = four_pillars(birth_date, time(branch * 2, 0), self.longitude, False)
            day = day_pillar(birth_date)
            hour = Pillar((2 * (day.stem % 5) + branch) % 10, branch)
            p = FourPillars(reference.year, reference.month, day, hour, reference.solar_time)
        else:
            p = four_pillars(birth_date, birth_time, self.longitude, self.late_zi_next_day)
        return SajuResult(p, weigh(p, self.harmony, self.climate))
