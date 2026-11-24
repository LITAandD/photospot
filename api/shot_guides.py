"""Public, opt-in cut finder. Never borrow a place centroid or personalized score."""
from datetime import date, time
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode
import json
import logging
import os

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from pipeline.catalog_visitors import today as kst_today
from pipeline.photo_permissions import allowed

DATA = Path(__file__).resolve().parents[1] / 'pipeline/data/shot_guides.json'
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

    @model_validator(mode='after')
    def ordered(self):
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


class Pin(Record):
    lat: float = Field(ge=37.55, le=37.59)
    lng: float = Field(ge=126.95, le=126.99)
    standing_landmark: str = Field(min_length=4)
    bearing_deg: float = Field(ge=0, lt=360)
    look_toward: str = Field(min_length=4)
    entry_instructions: str = Field(min_length=4)
    method: Literal['field_gnss_and_landmark', 'official_shooting_marker']
    evidence: Evidence


class Visual(Record):
    kind: Literal['diagram', 'photo'] = 'diagram'
    creator: str
    rights: str
    license_url: HttpUrl | None = None
    source_url: HttpUrl | None = None
    image_url: HttpUrl | None = None
    checked_at: date | None = None
    place_and_cut_verified: bool = False


class FieldReview(Record):
    checked_at: date
    valid_until: date
    record_ref: str = Field(min_length=4)
    first_time_tester_found_pin: bool
    framing_reproduced: bool
    safe_standing_area: bool


class Cut(Record):
    id: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{2,63}$')
    title: str
    status: Literal['candidate', 'verified', 'suspended'] = 'candidate'
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


class Place(Record):
    place_id: str
    name: str
    source_review: list[Evidence] = Field(default_factory=list)
    place_schedule: Schedule | None = None
    cuts: list[Cut]


def fresh(evidence, visit, today):
    return evidence is not None and evidence.checked_at <= today <= evidence.valid_until and evidence.checked_at <= visit <= evidence.valid_until


def schedule_status(schedule, visit, arrival, today):
    if not schedule or not fresh(schedule.source, visit, today):
        return 'unknown', '운영·접근 정보 확인 필요'
    windows = schedule.exceptions.get(visit, schedule.weekdays.get(str(visit.weekday())))
    if windows is None:
        return 'unknown', '해당 요일 운영정보 확인 필요'
    if not windows:
        return 'closed', schedule.exception_notes.get(visit, '선택일 정기 휴무')
    if schedule.admission_required and any(w.last_entry is None for w in windows):
        return 'unknown', '입장마감 확인 필요'
    if arrival is None:
        return 'conditional', '방문 시간 미선택 · 아래 개방시간과 입장마감을 확인해 주세요'
    if any(w.opens <= arrival < (w.last_entry or w.closes) for w in windows):
        return 'eligible', '확인된 운영시간 내 · 현장 통제 시 안내를 우선해 주세요'
    if any(w.last_entry is not None and w.last_entry <= arrival < w.closes for w in windows):
        return 'cutoff', '선택한 시간은 입장마감 이후예요'
    return 'closed', '선택한 시간은 개방시간 밖이에요'


def readiness(cut, visit, today):
    if cut.status != 'verified':
        return '촬영 위치·구도 검증 대기'
    field = cut.field_review
    if not field or not fresh(field, visit, today) or not all((field.first_time_tester_found_pin, field.framing_reproduced, field.safe_standing_area)):
        return '현장 재현·안전 검증 확인 필요'
    if not cut.pin or not fresh(cut.pin.evidence, visit, today) or not cut.framing:
        return '정확한 촬영 핀·방향 확인 필요'
    if cut.photography_allowed is False and fresh(cut.photography, visit, today):
        return '이 컷은 촬영이 제한된 구역이에요'
    if cut.photography_allowed is not True or not fresh(cut.photography, visit, today) or not cut.restrictions:
        return '컷별 촬영 제한 확인 필요'
    if not cut.goals or not cut.parties:
        return '동행·사진 목적 검수 필요'
    visual = cut.visual
    if not visual or not visual.creator or not visual.rights:
        return '구도 도식·사진 권리 확인 필요'
    if visual.kind == 'photo' and (not visual.place_and_cut_verified or not visual.checked_at or visual.checked_at > today
            or not visual.image_url or visual.image_url.scheme != 'https' or not visual.source_url or visual.source_url.scheme != 'https'
            or not allowed({'license_url': str(visual.license_url or '')})):
        return '사진 지점·사용 권리 확인 필요'
    return None


def load_places():
    try:
        raw = json.loads(DATA.read_text(encoding='utf8'))
        if raw['version'] != 1:
            raise ValueError('Unsupported version')
        places = [Place.model_validate(p) for p in raw['places']]
        ids = [c.id for p in places for c in p.cuts]
        if len(ids) != len(set(ids)) or len({p.place_id for p in places}) != len(places):
            raise ValueError('Duplicate place or cut')
        return places
    except (OSError, ValueError, KeyError, TypeError):
        logging.getLogger(__name__).error('shot_guides_unavailable')
        raise HTTPException(503, '촬영 안내를 확인하지 못했어요. 잠시 후 다시 시도해 주세요.') from None


def review_enabled():
    # A production deployment cannot enable synthetic records via APP_ENV or a URL.
    if os.environ.get('VERCEL_ENV'):
        return os.environ['VERCEL_ENV'] == 'preview'
    return not os.environ.get('VERCEL') and os.environ.get('APP_ENV') == 'test'


def choose(places, visit, arrival=None, party=None, goal=None, selected=None, today=None):
    today = today or kst_today()
    eligible, excluded = [], []
    all_cuts = {c.id: (p, c) for p in places for c in p.cuts}
    if selected and selected not in all_cuts:
        raise HTTPException(404, '이 컷을 찾지 못했어요. 다른 컷을 확인해 주세요.')
    for place in places:
        for cut in place.cuts:
            reason = readiness(cut, visit, today)
            statuses = [schedule_status(s, visit, arrival, today) for s in [place.place_schedule, cut.access]]
            # Confirmed closures/cutoffs take precedence over missing information.
            blocked = next((s for s in statuses if s[0] in ('closed', 'cutoff')), None)
            if blocked:
                reason = blocked[1]
            elif not reason:
                reason = next((s[1] for s in statuses if s[0] == 'unknown'), None)
            if not reason and goal and goal not in cut.goals:
                reason = '원하는 사진 유형과 다른 컷이에요'
            if reason:
                excluded.append({'cut_id': cut.id, 'title': cut.title, 'reason': reason})
            else:
                score = int(party in cut.parties) + int(goal in cut.goals)
                eligible.append((score, place, cut, statuses))
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
        windows = lambda s: [w.model_dump(mode='json') for w in s.exceptions.get(visit, s.weekdays.get(str(visit.weekday()), []))]
        return {'cut_id': c.id, 'place_id': p.place_id, 'place_name': p.name, 'title': c.title,
                'reason': ' · '.join(reason) if reason else '촬영 위치와 휴대폰 구도를 확인한 컷이에요',
                'pin': pin.model_dump(mode='json'), 'framing': c.framing,
                'navigation_url': 'https://www.google.com/maps/dir/?' + urlencode({'api': 1, 'destination': f'{pin.lat},{pin.lng}', 'travelmode': 'walking'}),
                'visual': c.visual.model_dump(mode='json'), 'restrictions': c.restrictions,
                'light_note': c.light_note if fresh(c.light_evidence, visit, today) else None,
                'availability': 'conditional' if arrival is None else 'eligible',
                'availability_note': statuses[0][1],
                'place_hours': windows(p.place_schedule), 'cut_hours': windows(c.access),
                'place_hours_note': p.place_schedule.note, 'cut_hours_note': c.access.note,
                'sources': [s.model_dump(mode='json') for s in [p.place_schedule.source, c.access.source, c.photography, pin.evidence]],
                'field_checked_at': c.field_review.checked_at.isoformat()}
    return {'date': visit.isoformat(), 'time': arrival.isoformat(timespec='minutes') if arrival else None,
            'primary': card(primary), 'alternative': card(alternative), 'replacement_reason': replacement_reason,
            'excluded': excluded, 'candidate_count': len(all_cuts), 'eligible_count': len(eligible),
            'empty_message': '이 조건에서 확인된 컷이 없어요' if not primary and not alternative else None}


@router.get('/preview/shots')
def shots(visit_date: date | None = None, arrival: str | None = Query(None, pattern=r'^([01]\d|2[0-3]):[0-5]\d$'),
          party: Party | None = None, goal: Goal | None = None,
          cut: str | None = Query(None, max_length=64), review_case: ReviewCase | None = None):
    visit = visit_date or kst_today()
    places = load_places()
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
    result = choose(places, visit, time.fromisoformat(arrival) if arrival else None, party, goal, cut)
    result.update(mode='review' if review_case else 'catalog', review_available=review_enabled())
    return result
