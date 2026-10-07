"""절기 계산용 천문 계산 (Meeus, Astronomical Algorithms 25장 저정밀 태양 위치, 오차 약 0.01° ≈ 15분).

절기는 태양 황경이 15° 배수가 되는 순간. 월주는 12절(節)로 나눈다.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

JD_UNIX_EPOCH = 2440587.5


def to_jd(dt: datetime) -> float:
    """timezone-aware datetime → Julian Day (UT). ΔT(~1분)는 무시한다."""
    return JD_UNIX_EPOCH + dt.astimezone(timezone.utc).timestamp() / 86400.0


def from_jd(jd: float) -> datetime:
    return datetime.fromtimestamp((jd - JD_UNIX_EPOCH) * 86400.0, tz=timezone.utc)


def jdn(d) -> int:
    """달력 날짜(그레고리력) → Julian Day Number (정오 기준 정수)."""
    a = (14 - d.month) // 12
    y = d.year + 4800 - a
    m = d.month + 12 * a - 3
    return d.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def solar_longitude(jd: float) -> float:
    """겉보기 태양 황경(도, 0~360)."""
    T = (jd - 2451545.0) / 36525.0
    L0 = 280.46646 + 36000.76983 * T + 0.0003032 * T * T
    M = math.radians(357.52911 + 35999.05029 * T - 0.0001537 * T * T)
    C = ((1.914602 - 0.004817 * T - 0.000014 * T * T) * math.sin(M)
         + (0.019993 - 0.000101 * T) * math.sin(2 * M) + 0.000289 * math.sin(3 * M))
    omega = math.radians(125.04 - 1934.136 * T)
    return (L0 + C - 0.00569 - 0.00478 * math.sin(omega)) % 360.0


def term_time(year: int, target_deg: float) -> datetime:
    """해당 연도(UTC 기준) 안에서 태양 황경이 target_deg가 되는 시각.
    315°(입춘)~285°(소한)까지 12절 모두 이 함수로 구한다."""
    # 대략적인 시작점: 춘분(0°) ≈ 3월 20일, 하루 약 0.9856°
    approx = datetime(year, 3, 20, tzinfo=timezone.utc) + timedelta(days=((target_deg % 360) / 360.0) * 365.2422)
    if target_deg >= 285:                          # 소한·입춘·경칩은 연초 (전년도 춘분 기준)
        approx -= timedelta(days=365.2422)
    jd = to_jd(approx)
    for _ in range(8):
        diff = (target_deg - solar_longitude(jd) + 180.0) % 360.0 - 180.0
        jd += diff / 360.0 * 365.2422
        if abs(diff) < 1e-6:
            break
    return from_jd(jd)


# 12절: 황경 → (지지 인덱스, 이름). 寅=2 부터.
SOLAR_TERMS = [
    (315, 2, "입춘"), (345, 3, "경칩"), (15, 4, "청명"), (45, 5, "입하"), (75, 6, "망종"), (105, 7, "소서"),
    (135, 8, "입추"), (165, 9, "백로"), (195, 10, "한로"), (225, 11, "입동"), (255, 0, "대설"), (285, 1, "소한"),
]


def terms_around(dt_utc: datetime) -> list[tuple[datetime, int, str]]:
    """dt 앞뒤로 월주 판정에 필요한 절 목록 (전년도 소한부터 다음 해 입춘까지)."""
    out = []
    for y in (dt_utc.year - 1, dt_utc.year, dt_utc.year + 1):
        for deg, branch, name in SOLAR_TERMS:
            out.append((term_time(y, deg), branch, name))
    return sorted(out)
