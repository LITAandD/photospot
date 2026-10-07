"""생년월일시 → 사주 네 기둥(년·월·일·시).

시간 보정 순서: 입력(당시 한국 표준시) → 서머타임 해제 → UTC → 시태양시(동경 127.5° 기준, KST−30분)
- 년주: 입춘 기준. 월주: 12절 기준. 일주: 율리우스일 기준. 시주: 시태양시 기준 12시진.
- 야자시(23~24시)는 기본적으로 그날의 子시로 본다 (다음 날로 넘기려면 late_zi_next_day=True).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from .astro import jdn, terms_around

STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
STEMS_KO = "갑을병정무기경신임계"
BRANCHES_KO = "자축인묘진사오미신유술해"

# 한국 표준시 이력 (UTC+8:30 구간). 그 외는 UTC+9.
UTC_830_PERIODS = [
    (datetime(1908, 4, 1), datetime(1912, 1, 1)),
    (datetime(1954, 3, 21), datetime(1961, 8, 10)),
]
# 한국 서머타임 시행 구간 (시계를 1시간 앞당김)
DST_PERIODS = [
    (datetime(1948, 6, 1), datetime(1948, 9, 13)), (datetime(1949, 4, 3), datetime(1949, 9, 11)),
    (datetime(1950, 4, 1), datetime(1950, 9, 10)), (datetime(1951, 5, 6), datetime(1951, 9, 9)),
    (datetime(1955, 5, 5), datetime(1955, 9, 9)), (datetime(1956, 5, 20), datetime(1956, 9, 30)),
    (datetime(1957, 5, 5), datetime(1957, 9, 22)), (datetime(1958, 5, 4), datetime(1958, 9, 21)),
    (datetime(1959, 5, 3), datetime(1959, 9, 20)), (datetime(1960, 5, 1), datetime(1960, 9, 18)),
    (datetime(1987, 5, 10, 2), datetime(1987, 10, 11, 3)), (datetime(1988, 5, 8, 2), datetime(1988, 10, 9, 3)),
]


@dataclass(frozen=True)
class Pillar:
    stem: int      # 0~9 (甲=0)
    branch: int    # 0~11 (子=0)

    @property
    def hanja(self) -> str:
        return STEMS[self.stem] + BRANCHES[self.branch]

    @property
    def hangul(self) -> str:
        return STEMS_KO[self.stem] + BRANCHES_KO[self.branch]


@dataclass(frozen=True)
class FourPillars:
    year: Pillar
    month: Pillar
    day: Pillar
    hour: Pillar | None          # 태어난 시간 모르면 None
    solar_time: datetime         # 보정된 시태양시 (naive)

    def as_dict(self) -> dict:
        return {k: {"hanja": p.hanja, "hangul": p.hangul} for k, p in
                (("year", self.year), ("month", self.month), ("day", self.day), ("hour", self.hour)) if p}


def _in(dt: datetime, periods) -> bool:
    return any(s <= dt < e for s, e in periods)


def to_utc(local: datetime) -> datetime:
    """당시 한국 표준시(naive) → UTC."""
    if _in(local, DST_PERIODS):
        local = local - timedelta(hours=1)
    offset = timedelta(hours=8, minutes=30) if _in(local, UTC_830_PERIODS) else timedelta(hours=9)
    return (local - offset).replace(tzinfo=timezone.utc)


def sexagenary(index: int) -> Pillar:
    return Pillar(index % 10, index % 12)


def year_pillar(dt_utc: datetime, terms) -> Pillar:
    ipchun = [t for t, branch, name in terms if name == "입춘"]
    year = dt_utc.year
    # 이 해의 입춘 전이면 전년도
    this_year_ipchun = next(t for t in ipchun if t.year == year)
    if dt_utc < this_year_ipchun:
        year -= 1
    return sexagenary((year - 1984) % 60)           # 1984 = 甲子년


def month_pillar(dt_utc: datetime, year_stem: int, terms) -> Pillar:
    past = [(t, b) for t, b, _ in terms if t <= dt_utc]
    _, branch = past[-1]
    m = (branch - 2) % 12                            # 寅=0
    stem = (2 * (year_stem % 5) + 2 + m) % 10        # 오호둔
    return Pillar(stem, branch)


def day_pillar(solar_date: date) -> Pillar:
    return sexagenary((jdn(solar_date) + 49) % 60)   # 2000-01-01 = 戊午


def hour_pillar(solar_time: time, day_stem: int) -> Pillar:
    minutes = solar_time.hour * 60 + solar_time.minute
    branch = ((minutes + 60) // 120) % 12            # 23:00~00:59 = 子
    stem = (2 * (day_stem % 5) + branch) % 10        # 오서둔
    return Pillar(stem, branch)


def four_pillars(birth_date: date, birth_time: time | None, longitude: float = 127.5,
                 late_zi_next_day: bool = False) -> FourPillars:
    """birth_time이 None이면 정오로 놓고 시주는 생략. longitude: 시태양시 기준 경도(기본 동경 127.5° = KST−30분)."""
    t = birth_time or time(12, 0)
    utc = to_utc(datetime.combine(birth_date, t))
    solar = (utc + timedelta(hours=longitude / 15.0)).replace(tzinfo=None)
    terms = terms_around(utc)
    yp = year_pillar(utc, terms)
    mp = month_pillar(utc, yp.stem, terms)
    day_date = solar.date()
    if late_zi_next_day and solar.hour == 23:
        day_date = day_date + timedelta(days=1)
    dp = day_pillar(day_date)
    hp = hour_pillar(solar.time(), dp.stem) if birth_time else None
    return FourPillars(yp, mp, dp, hp, solar)
