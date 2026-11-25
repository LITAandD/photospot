"""Public, opt-in cut finder. Never borrow a place centroid or personalized score."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlencode
import json
import logging
import os

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, model_validator

from pipeline.catalog_visitors import today as kst_today
from pipeline.photo_permissions import allowed

DATA = Path(__file__).resolve().parents[1] / 'pipeline/data/shot_guides.json'
MIN_ENTRY_PLACES = 3
MAX_SCHEDULE_DAYS = 31
Party = Literal['solo', 'pair', 'family']
Goal = Literal['portrait', 'architecture', 'landscape']
ReviewCase = Literal['open', 'weekly_closed', 'cutoff', 'temporary_closed', 'unknown', 'no_alternative']
router = APIRouter()


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Evidence(Record):
    label: str
    url: HttpUrl
    checked_at: date
    valid_until: date

    @model_validator(mode='after')
    def dates(self):
        if self.url.scheme != 'https' or self.valid_until < self.checked_at:
            raise ValueError('HTTPS source and ordered review dates required')
        return self


class Window(Record):
    opens: time
    closes: time
    last_entry: time | None = None
    all_day: bool = False

    @model_validator(mode='after')
    def ordered(self):
        if self.all_day:
            if self.opens != time(0) or self.closes != time(0) or self.last_entry is not None:
                raise ValueError('All-day window uses 00:00 boundaries and no admission cutoff')
            return self
        if self.opens >= self.closes or self.last_entry is not None and not self.opens < self.last_entry <= self.closes:
            raise ValueError('Same-day opening and entry windows required')
        return self


class Schedule(Record):
    source: Evidence
    # All weekdays are explicit. Empty means confirmed closed, absent means unknown.
    weekdays: dict[str, list[Window]]
    exceptions: dict[date, list[Window]] = Field(default_factory=dict)
    exception_notes: dict[date, str] = Field(default_factory=dict)
    admission_required: bool = True
    note: str
    applies_from: date | None = None
    applies_until: date | None = None

    @model_validator(mode='after')
    def calendar(self):
        if set(self.weekdays) - {str(i) for i in range(7)} or set(self.exception_notes) - set(self.exceptions):
            raise ValueError('Weekdays are 0=Monday through 6=Sunday; notes require exceptions')
        if (self.applies_from is None) != (self.applies_until is None):
            raise ValueError('Both schedule applicability bounds are required')
        if self.applies_from and self.applies_until < self.applies_from:
            raise ValueError('Ordered applicability bounds required')
        for windows in [*self.weekdays.values(), *self.exceptions.values()]:
            if any(w.all_day for w in windows) and (len(windows) != 1 or self.admission_required):
                raise ValueError('All-day access must be a single window without admission')
            ordered = sorted(windows, key=lambda w: w.opens)
            if any(a.closes > b.opens for a, b in zip(ordered, ordered[1:])):
                raise ValueError('Overlapping windows')
        return self


class Pin(Record):
    lat: float = Field(ge=37.55, le=37.59)
    lng: float = Field(ge=126.95, le=126.99)
    standing_landmark: str = Field(min_length=4)
    bearing_deg: float = Field(ge=0, lt=360)
    look_toward: str = Field(min_length=4)
    entry_instructions: str = Field(min_length=4)
    method: Literal['field_gnss_and_landmark', 'official_shooting_marker']
    evidence: Evidence | None = None
    accuracy_m: float | None = Field(None, gt=0, le=15)

    @model_validator(mode='after')
    def provenance(self):
        if self.method == 'field_gnss_and_landmark' and (self.evidence is not None or self.accuracy_m is None):
            raise ValueError('Field pins require accuracy and private field record, not a public evidence URL')
        if self.method == 'official_shooting_marker' and self.evidence is None:
            raise ValueError('Official shooting marker requires a public source')
        return self


class Composition(Record):
    subject: Goal
    orientation: Literal['portrait', 'landscape']
    subject_x: float = Field(ge=0.15, le=0.85)


class Visual(Record):
    kind: Literal['diagram', 'photo'] = 'diagram'
    creator: str
    rights: str
    license_url: HttpUrl | None = None
    source_url: HttpUrl | None = None
    image_url: HttpUrl | None = None
    checked_at: date | None = None
    place_and_cut_verified: bool = False
    composition: Composition | None = None
    width: int | None = Field(None, gt=0, le=30000)
    height: int | None = Field(None, gt=0, le=30000)


class FieldReview(Record):
    checked_at: date
    valid_until: date
    record_ref: str = Field(min_length=4)
    first_time_tester_found_pin: bool
    framing_reproduced: bool
    safe_standing_area: bool
    independent_measurement: bool = False
    catalog_overlap_reviewed: bool = False

    @model_validator(mode='after')
    def ordered(self):
        if self.valid_until < self.checked_at:
            raise ValueError('Ordered field review dates required')
        return self


class Cut(Record):
    id: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{2,63}$')
    title: str
    status: Literal['candidate', 'verified', 'suspended'] = 'candidate'
    area: Literal['inside_place', 'public_outdoor'] = 'inside_place'
    pin: Pin | None = None
    framing: str | None = None
    parties: list[Party] = Field(default_factory=list)
    goals: list[Goal] = Field(default_factory=list)
    visual: Visual | None = None
    field_review: FieldReview | None = None
    access: Schedule | None = None
    photography: Evidence | None = None
    photography_allowed: bool | None = None
    restrictions: str | None = None
    light_note: str | None = None
    light_evidence: Evidence | None = None
    pending: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def pending_review(self):
        if self.status == 'verified' and self.pending:
            raise ValueError('Verified cut cannot have unresolved review items')
        return self


class Place(Record):
    place_id: str
    name: str
    source_review: list[Evidence] = Field(default_factory=list)
    place_schedule: Schedule | None = None
    cuts: list[Cut]
    max_pin_distance_m: float = Field(500, gt=0, le=2000)
    pin_distance_note: str | None = None

    @model_validator(mode='after')
    def distance_exception(self):
        if self.max_pin_distance_m > 500 and not self.pin_distance_note:
            raise ValueError('Large-place distance exception needs a review note')
        return self


class CatalogData(Record):
    version: Literal[1]
    places: list[Place]

    @model_validator(mode='after')
    def unique_ids(self):
        ids = [c.id for p in self.places for c in p.cuts]
        if len(ids) != len(set(ids)) or len({p.place_id for p in self.places}) != len(self.places):
            raise ValueError('Duplicate place or cut')
        return self


def windows_for(schedule, visit):
    if not schedule or not schedule.applies_from or not schedule.applies_from <= visit <= schedule.applies_until:
        return None
    return schedule.exceptions.get(visit, schedule.weekdays.get(str(visit.weekday())))


def schedules_for(place, cut):
    return [cut.access] if cut.area == 'public_outdoor' else [place.place_schedule, cut.access]


def pin_location_issue(place, cut, catalog_place):
    from math import radians, sin, cos, asin, sqrt
    if not cut.pin or not catalog_place:
        return '촬영 핀 위치 재확인 필요'
    pin = cut.pin
    lat, lng = catalog_place['lat'], catalog_place['lng']
    a = sin(radians(pin.lat-lat)/2)**2 + cos(radians(lat))*cos(radians(pin.lat))*sin(radians(pin.lng-lng)/2)**2
    distance = 6371000 * 2 * asin(min(1, sqrt(a)))
    if distance > place.max_pin_distance_m:
        return '촬영 핀 위치 재확인 필요'
    if distance <= 3 and not (cut.field_review and cut.field_review.independent_measurement and cut.field_review.catalog_overlap_reviewed):
        return '카탈로그 좌표와 겹치는 촬영 핀 재검수 필요'
    return None


def fresh(evidence, visit, today):
    return evidence is not None and evidence.checked_at <= today <= evidence.valid_until and evidence.checked_at <= visit <= evidence.valid_until


def schedule_status(schedule, visit, arrival, today, now_t=None):
    if not schedule or not fresh(schedule.source, visit, today):
        return 'unknown', '운영·접근 정보 확인 필요'
    if (schedule.source.valid_until - schedule.source.checked_at).days > MAX_SCHEDULE_DAYS:
        return 'unknown', '운영 정보 재확인 필요'
    windows = windows_for(schedule, visit)
    note = schedule.exception_notes.get(visit)
    def result(status, message):
        return status, message + (' · ' + note if note else '')
    if windows is None:
        return 'unknown', '해당 날짜 운영정보 확인 필요'
    if not windows:
        return 'closed', note or ('선택일 임시 휴무·통제' if visit in schedule.exceptions else '선택일 정기 휴무')
    if schedule.admission_required and any(w.last_entry is None for w in windows):
        return 'unknown', '입장마감 확인 필요'
    if now_t is not None and arrival is not None and arrival < now_t:
        return result('closed', '이미 지난 시간이에요')
    if now_t is not None and arrival is None and not any(w.all_day or now_t < (w.last_entry or w.closes) for w in windows):
        return result('cutoff', '오늘 입장마감 시간이 지났어요')
    if arrival is None:
        return result('conditional', '방문 시간 미선택 · 아래 개방시간과 입장마감을 확인해 주세요')
    if any(w.all_day or w.opens <= arrival < (w.last_entry or w.closes) for w in windows):
        return result('eligible', '확인된 운영시간 내 · 현장 통제 시 안내를 우선해 주세요')
    later = min((w.opens for w in windows if w.opens > arrival), default=None)
    if later is not None:
        return result('closed', f'{later:%H:%M}부터 입장할 수 있어요')
    if any(w.last_entry is not None and w.last_entry <= arrival < w.closes for w in windows):
        return result('cutoff', '선택한 시간은 입장마감 이후예요')
    return result('closed', '선택한 시간은 개방시간 밖이에요')


def readiness(cut, visit, today):
    if cut.status == 'suspended':
        return '현재 이 컷 안내를 일시 중단했어요'
    if cut.photography_allowed is False and fresh(cut.photography, visit, today):
        return '이 컷은 촬영이 제한된 구역이에요'
    if cut.status != 'verified':
        return '촬영 위치·구도 검증 대기'
    field = cut.field_review
    if not field or not fresh(field, visit, today) or not all((field.first_time_tester_found_pin, field.framing_reproduced, field.safe_standing_area)):
        return '현장 재현·안전 검증 확인 필요'
    if not cut.pin or not cut.framing:
        return '정확한 촬영 핀·방향 확인 필요'
    if cut.pin.method == 'official_shooting_marker' and not fresh(cut.pin.evidence, visit, today):
        return '공식 촬영 표식 재확인 필요'
    if cut.pin.method == 'field_gnss_and_landmark' and not field.independent_measurement:
        return '독립 측정 기록 확인 필요'
    if cut.photography_allowed is False and fresh(cut.photography, visit, today):
        return '이 컷은 촬영이 제한된 구역이에요'
    if cut.photography_allowed is not True or not fresh(cut.photography, visit, today) or not cut.restrictions:
        return '컷별 촬영 제한 확인 필요'
    if not cut.goals or not cut.parties:
        return '동행·사진 목적 검수 필요'
    visual = cut.visual
    if not visual or not visual.creator or not visual.rights:
        return '구도 도식·사진 권리 확인 필요'
    if visual.kind == 'diagram' and visual.composition is None:
        return '구도 도식 구성 검수 필요'
    if visual.kind == 'photo' and (not visual.place_and_cut_verified or not visual.checked_at or visual.checked_at > today
            or not visual.image_url or visual.image_url.scheme != 'https' or not visual.source_url or visual.source_url.scheme != 'https'
            or not allowed({'license_url': str(visual.license_url or '')})):
        return '사진 지점·사용 권리 확인 필요'
    return None


def read_records(path=None):
    return CatalogData.model_validate(json.loads(Path(path or DATA).read_text(encoding='utf8'))).places


def validation_location(exc):
    error = exc.errors(include_input=False, include_context=False)[0]
    return '.'.join(map(str, error['loc'])), error['type']


def load_places():
    try:
        return read_records()
    except ValidationError as exc:
        loc, kind = validation_location(exc)
        logging.getLogger(__name__).error('shot_guides_invalid loc=%s type=%s', loc, kind)
    except (OSError, ValueError, KeyError, TypeError):
        logging.getLogger(__name__).error('shot_guides_unavailable')
    raise HTTPException(503, '촬영 안내를 확인하지 못했어요. 잠시 후 다시 시도해 주세요.') from None


def review_enabled():
    # A production deployment cannot enable synthetic records via APP_ENV or a URL.
    if os.environ.get('VERCEL_ENV'):
        return os.environ['VERCEL_ENV'] == 'preview'
    return not os.environ.get('VERCEL') and os.environ.get('APP_ENV') == 'test'


def choose(places, visit, arrival=None, party=None, goal=None, selected=None, today=None, catalog_places=None, now=None, entry_only=False):
    now = now or datetime.now(ZoneInfo('Asia/Seoul'))
    today = today or kst_today() # Injectable clock/date for deterministic callers.
    clock_day = now.astimezone(ZoneInfo('Asia/Seoul')).date()
    now_t = now.astimezone(ZoneInfo('Asia/Seoul')).time().replace(second=0, microsecond=0) if visit == today == clock_day else None
    goal_counts = {g: 0 for g in ('portrait', 'architecture', 'landscape')}
    eligible, excluded = [], []
    all_cuts = {c.id: (p, c) for p in places for c in p.cuts}
    if selected and selected not in all_cuts:
        raise HTTPException(404, '이 컷을 찾지 못했어요. 다른 컷을 확인해 주세요.')
    for place in places:
        for cut in place.cuts:
            reason = readiness(cut, visit, today)
            statuses = [schedule_status(s, visit, arrival, today, now_t) for s in schedules_for(place, cut)]
            # Confirmed closures/cutoffs take precedence over missing information.
            blocked = next((s for s in statuses if s[0] in ('closed', 'cutoff')), None)
            hard = cut.status == 'suspended' or (cut.photography_allowed is False and fresh(cut.photography, visit, today))
            if blocked and not hard:
                reason = blocked[1]
            elif not reason:
                reason = next((s[1] for s in statuses if s[0] == 'unknown'), None)
            if not reason and catalog_places is not None:
                reason = pin_location_issue(place, cut, catalog_places.get(place.place_id))
            code = 'pending' if cut.status == 'candidate' else 'unverified'
            if hard: code = 'restricted'
            elif blocked: code = blocked[0]
            if not reason:
                for g in set(cut.goals): goal_counts[g] += 1
            if not reason and goal and goal not in cut.goals:
                code = 'purpose'
                reason = '원하는 사진 유형과 다른 컷이에요'
            if reason:
                excluded.append({'cut_id': cut.id, 'title': cut.title, 'reason': reason, 'code': code})
            else:
                score = int(party in cut.parties) + int(goal in cut.goals)
                eligible.append((score, place, cut, statuses))
    entry = {'date': visit.isoformat(),
             'entry_ready': len({r[1].place_id for r in eligible}) >= MIN_ENTRY_PLACES
                 and {'portrait', 'architecture'} <= {g for r in eligible for g in r[2].goals}}
    if entry_only:
        # Same eligibility gates; skip sorting and serializing unused cards/photos/sources.
        return entry
    eligible.sort(key=lambda row: (-row[0], row[2].id))
    selected_cut = all_cuts.get(selected, (None, None))[1]
    primary = next((r for r in eligible if r[2].id == selected), None) if selected else next(iter(eligible), None)
    replacement_reason, alternative = None, None
    if selected and not primary:
        replacement_reason = next(e['reason'] for e in excluded if e['cut_id'] == selected)
        # Do not silently switch to another purpose or use an unverified substitute.
        target = {goal} if goal else set(selected_cut.goals)
        alternative = next((r for r in eligible if target.intersection(r[2].goals)), None)
    def card(row):
        if row is None:
            return None
        _, p, c, statuses = row
        reason = []
        if party in c.parties:
            reason.append({'solo': '혼자 따라 찍는', 'pair': '둘이 담는', 'family': '가족이 함께 담는'}[party])
        if goal in c.goals:
            reason.append({'portrait': '인물', 'architecture': '건축', 'landscape': '풍경'}[goal] + ' 구도')
        pin = c.pin
        windows = lambda s: [w.model_dump(mode='json') for w in (windows_for(s, visit) or [])]
        source_pairs = [*([('place_hours',p.place_schedule.source)] if c.area != 'public_outdoor' else []),
                        ('cut_access',c.access.source), ('photography',c.photography), ('pin',pin.evidence)]
        if c.light_note and fresh(c.light_evidence,visit,today): source_pairs.append(('light',c.light_evidence))
        sources = {}
        for kind, source in source_pairs:
            if source is None: continue
            key = (str(source.url),source.label,source.checked_at,source.valid_until)
            if key not in sources: sources[key] = {**source.model_dump(mode='json'), 'kinds': []}
            sources[key]['kinds'].append(kind)
        return {'cut_id': c.id, 'place_id': p.place_id, 'place_name': p.name, 'title': c.title,
                'reason': ' · '.join(reason) if reason else '촬영 위치와 휴대폰 구도를 확인한 컷이에요',
                'pin': pin.model_dump(mode='json', exclude={'evidence'}), 'framing': c.framing,
                'navigation': {
                    'kakao': f'https://map.kakao.com/link/to/{quote(p.name + " 촬영 위치", safe="")},{pin.lat},{pin.lng}',
                    'naver': 'nmap://route/walk?' + urlencode({'dlat': pin.lat, 'dlng': pin.lng, 'dname': p.name + ' 촬영 위치', 'appname': 'https://photospot.litaandd.com'}),
                    'google': 'https://www.google.com/maps/search/?' + urlencode({'api': 1, 'query': f'{pin.lat},{pin.lng}'})},
                'visual': c.visual.model_dump(mode='json'), 'restrictions': c.restrictions,
                'light_note': c.light_note if fresh(c.light_evidence, visit, today) else None,
                'availability': 'conditional' if arrival is None else 'eligible',
                'availability_note': ' · '.join(dict.fromkeys(s[1] for s in statuses)),
                'place_hours': [] if c.area == 'public_outdoor' else windows(p.place_schedule), 'cut_hours': windows(c.access),
                'place_hours_note': '공공 야외 공간 · 장소 운영시간과 별개' if c.area == 'public_outdoor' else p.place_schedule.note, 'cut_hours_note': c.access.note,
                'sources': list(sources.values()),
                'field_checked_at': c.field_review.checked_at.isoformat()}
    return {**entry, 'time': arrival.isoformat(timespec='minutes') if arrival else None,
            'primary': card(primary), 'alternative': card(alternative), 'replacement_reason': replacement_reason,
            'goal_counts': goal_counts, 'excluded': excluded, 'candidate_count': len(all_cuts), 'eligible_count': len(eligible),
            'empty_message': '이 조건에서 확인된 컷이 없어요' if not primary and not alternative else None}


@router.get('/preview/shots')
def shots(visit_date: date | None = None, arrival: str | None = Query(None, pattern=r'^([01]\d|2[0-3]):[0-5]\d$'),
          party: Party | None = None, goal: Goal | None = None,
          cut: str | None = Query(None, max_length=64), review_case: ReviewCase | None = None, view: Literal['full', 'entry'] = 'full'):
    today = kst_today()
    visit = visit_date or today
    if not today <= visit <= today + timedelta(days=366):
        raise HTTPException(422, '방문일은 오늘부터 1년 이내로 선택해 주세요')
    places = load_places()
    active = None
    if review_case:
        if not review_enabled():
            raise HTTPException(404, '검토용 화면은 미리보기에서만 제공해요')
        from .shot_review import fixture_places
        places = fixture_places(review_case, visit)
    else:
        # Active catalog membership only; never substitute its lat/lng for a pin.
        from .catalog_bridge import find_many
        active = find_many([p.place_id for p in places])
        places = [p for p in places if p.place_id in active]
    result = choose(places, visit, time.fromisoformat(arrival) if arrival else None, party, goal, cut, today=today, catalog_places=active, entry_only=view == 'entry')
    if review_case:
        result['entry_ready'] = False
    result['mode'] = 'review' if review_case else 'catalog'
    if view == 'full': result['review_available'] = review_enabled()
    return result


def catalog_records(path=None):
    import sqlite3
    root = Path(__file__).resolve().parents[1]
    target = Path(path or os.environ.get('PLACE_CATALOG_DB') or root / 'catalog/places.sqlite3').resolve()
    with sqlite3.connect(target.as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        return {r['id']: dict(r) for r in conn.execute('SELECT id,lat,lng FROM places WHERE active=1')}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description='Validate shot evidence without changing catalog or publishing pins')
    ap.add_argument('command', choices=['check'])
    ap.add_argument('--path', type=Path, default=DATA)
    ap.add_argument('--catalog', type=Path)
    ap.add_argument('--date', type=date.fromisoformat, default=kst_today())
    args = ap.parse_args(argv)
    try:
        places = read_records(args.path)
        active = catalog_records(args.catalog)
    except ValidationError as exc:
        print(*validation_location(exc))
        return 1
    except (ValueError, OSError):
        print('catalog invalid_or_unreadable')
        return 1
    bad = False
    print('place_id | cut_id | status | readiness | schedule')
    for p in places:
        for c in p.cuts:
            reason = readiness(c, args.date, kst_today())
            if c.status == 'verified':
                reason = reason or pin_location_issue(p, c, active.get(p.place_id))
            states = [schedule_status(s, args.date, None, kst_today()) for s in schedules_for(p,c)]
            print(f'{p.place_id} | {c.id} | {c.status} | {reason or "ready"} | ' + ' / '.join(s[1] for s in states))
            bad |= p.place_id not in active or c.status == 'verified' and (reason is not None or any(s[0]=='unknown' for s in states))
    return int(bad)


if __name__ == '__main__':
    raise SystemExit(main())
