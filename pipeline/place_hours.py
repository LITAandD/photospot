"""Reviewed public Naver Place schedules, kept separate from live open/closed status."""
from calendar import monthrange
from datetime import date, datetime
from functools import lru_cache
import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .place_catalog import distance_m

DATA = Path(__file__).with_name('data') / 'place_hours.json'
DAYS = ['월', '화', '수', '목', '금', '토', '일']


class WeekSchedule(BaseModel):
    model_config = ConfigDict(extra='forbid')
    week: list[str] = Field(min_length=7, max_length=7)

    @field_validator('week')
    @classmethod
    def complete_week(cls, week):
        if any(not text.strip() for text in week):
            raise ValueError('All seven days need reviewed hours or an explicit closure')
        return week


class SeasonalHours(WeekSchedule):
    months: list[int] = Field(min_length=1, max_length=12)

    @field_validator('months')
    @classmethod
    def valid_months(cls, months):
        if len(set(months)) != len(months) or any(not 1 <= month <= 12 for month in months):
            raise ValueError('Seasonal months must be unique values from 1 to 12')
        return months


class MonthlyClosure(BaseModel):
    model_config = ConfigDict(extra='forbid')
    weekday: int = Field(ge=0, le=6)
    occurrence: Literal[-1, 1, 2, 3, 4, 5]
    label: str = Field(min_length=1)

    def applies(self, day):
        if day.weekday() != self.weekday:
            return False
        return (day.day + 7 > monthrange(day.year, day.month)[1] if self.occurrence == -1
                else (day.day - 1) // 7 + 1 == self.occurrence)


class ReviewedHours(WeekSchedule):
    place_id: str
    place_name: str
    branch_name: str
    lat: float = Field(ge=33, le=39)
    lng: float = Field(ge=124, le=132)
    address: str = Field(min_length=1)
    seasonal_hours: list[SeasonalHours] = Field(default_factory=list)
    monthly_closures: list[MonthlyClosure] = Field(default_factory=list)
    date_overrides: dict[date, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    source_url: str
    checked_at: date

    @model_validator(mode='after')
    def validate_source(self):
        url = urlsplit(self.source_url)
        if (url.scheme != 'https' or url.hostname not in {'map.naver.com', 'pcmap.place.naver.com', 'm.place.naver.com', 'search.naver.com'}
                or url.username or url.password or url.port):
            raise ValueError('Use the original public Naver Place page')
        months = [month for season in self.seasonal_hours for month in season.months]
        if len(months) != len(set(months)):
            raise ValueError('Seasonal schedules must not overlap')
        if any(not value.strip() for value in self.date_overrides.values()):
            raise ValueError('A date override needs explicit hours or closure')
        if self.checked_at > datetime.now(ZoneInfo('Asia/Seoul')).date(): raise ValueError('Future observation date')
        return self


@lru_cache(maxsize=1)
def reviewed_hours():
    entries = [ReviewedHours.model_validate(row) for row in json.loads(DATA.read_text(encoding='utf-8'))]
    if len({e.place_id for e in entries}) != len(entries): raise ValueError('Duplicate branch')
    return {e.place_id: e for e in entries}


def hours_for(place, visit_date, today=None):
    today = today or datetime.now(ZoneInfo('Asia/Seoul')).date()
    visit_date = date.fromisoformat(visit_date) if isinstance(visit_date, str) else visit_date
    from . import official_place_hours, osm_place_hours
    official = official_place_hours.hours_for(place, visit_date, today)
    if official: return official
    entry = reviewed_hours().get(place['id'])
    if (not entry or entry.place_name != place['name'] or
            distance_m(entry.lat, entry.lng, place) > 100):
        return osm_place_hours.hours_for(place, visit_date, today)
    age = (today - entry.checked_at).days
    if age < 0: return None
    week = next((season.week for season in entry.seasonal_hours if visit_date.month in season.months), entry.week)
    visit_hours = next((rule.label for rule in entry.monthly_closures if rule.applies(visit_date)),
                       week[visit_date.weekday()])
    visit_hours = entry.date_overrides.get(visit_date, visit_hours)
    notes = list(entry.notes)
    if entry.seasonal_hours:
        notes.insert(0, f'촬영월 {visit_date.month}월 기준 관람시간')
    groups = {}
    for day, hours in enumerate(week): groups.setdefault(hours, []).append(day)
    lines = []
    for hours, days in groups.items():
        label = '매일' if len(days) == 7 else '월–금' if days == [0, 1, 2, 3, 4] else '·'.join(DAYS[d] for d in days)
        lines.append(f'{label} {hours}')
    stale = age > 30
    basis = '특별 일정' if visit_date in entry.date_overrides else '정규'
    summary = '영업시간 재확인 필요' if stale else f'{DAYS[visit_date.weekday()]} {visit_hours} ({basis})'
    return {'provider': 'naver', 'source_label': '네이버지도', 'source_url': entry.source_url,
            'checked_at': entry.checked_at.isoformat(), 'stale': stale, 'summary': summary,
            'weekly_hours': lines, 'notes': notes, 'address': entry.address,
            'branch_name': entry.branch_name}
