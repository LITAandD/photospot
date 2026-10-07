"""Date-specific hours published by official branches; never extrapolate a week.

Refresh is an explicit, serial command. Application requests only read the
checked manifest. A 403/429 stops the import; no retries or alternate endpoints.
"""
import argparse
from datetime import date, datetime, timedelta
from functools import lru_cache
import json
from pathlib import Path
import re
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import place_catalog as catalog, official_cafe_photos as official

DATA = Path(__file__).with_name('data') / 'official_place_hours.json'
DAYS = ['월', '화', '수', '목', '금', '토', '일']


class DatedHours(BaseModel):
    model_config = ConfigDict(extra='forbid')
    place_id: str
    store_id: str = Field(pattern=r'^\d+$')
    branch: str
    lat: float = Field(ge=33, le=39)
    lng: float = Field(ge=124, le=132)
    address: str
    checked_at: date
    date_hours: dict[date, str] = Field(min_length=1, max_length=7)

    @model_validator(mode='after')
    def valid_dates(self):
        if self.checked_at > datetime.now(ZoneInfo('Asia/Seoul')).date():
            raise ValueError('Future observation date')
        for day, hours in self.date_hours.items():
            if not self.checked_at <= day <= self.checked_at + timedelta(days=6) or not hours.strip():
                raise ValueError('Hours must belong to the observed seven-day window')
        return self


@lru_cache(maxsize=1)
def entries():
    if not DATA.exists(): return {}
    rows = [DatedHours.model_validate(row) for row in json.loads(DATA.read_text(encoding='utf-8'))]
    if len({r.place_id for r in rows}) != len(rows): raise ValueError('Duplicate official branch')
    return {r.place_id: r for r in rows}


def hours_for(place, visit_date, today):
    entry = entries().get(place['id'])
    if not entry or not official.valid_branch(place, entry.model_dump()) or entry.checked_at > today:
        return None
    first, last = min(entry.date_hours), max(entry.date_hours)
    stale = today > last
    selected = entry.date_hours.get(visit_date)
    summary = (f'{DAYS[visit_date.weekday()]} {selected} (공식 날짜별)' if selected and not stale
               else '촬영일 운영시간 · 공식 안내 확인')
    return {'provider': 'official', 'schedule_kind': 'dated', 'source_label': '스타벅스 공식 매장 안내',
            'source_url': official.SITE + '/store/store_map.do?in_biz_cd=' + entry.store_id,
            'checked_at': entry.checked_at.isoformat(), 'stale': stale, 'summary': summary,
            'weekly_hours': [f'{day:%Y-%m-%d} ({DAYS[day.weekday()]}) {hours}' for day, hours in sorted(entry.date_hours.items())],
            'notes': [f'공식 게시 일정: {first:%Y-%m-%d} ~ {last:%Y-%m-%d}',
                      '게시된 날짜에만 적용해요. 다른 날짜의 운영시간은 공식 안내에서 확인해 주세요.'],
            'address': entry.address, 'branch_name': entry.branch}


def parse_schedule(rows, observed):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 7:
        raise ValueError('Missing or oversized official schedule')
    schedule = {}
    for offset, row in enumerate(rows):
        day = observed + timedelta(days=offset)
        # The source gives day-of-month and Sunday=1 weekday, not year/month.
        # Only a sequence anchored to the observation date is unambiguous.
        if int(row['store_time_day']) != day.day or int(row['store_time_week']) != (day.weekday()+1) % 7 + 1:
            raise ValueError('Source schedule date differs from observation date')
        flag = str(row.get('store_time_hlytag', ''))
        raw = str(row.get('store_opentime') or '').replace(' ', '')
        if flag == '4':
            schedule[day] = '휴점'
            continue
        match = re.fullmatch(r'(\d{2})([0-5]\d)-(\d{2})([0-5]\d)', raw)
        if not match: raise ValueError('Unpublished or malformed hours')
        sh, sm, eh, em = match.groups()
        if int(sh) > 23 or int(eh) > 24 or (eh == '24' and em != '00'):
            raise ValueError('Invalid clock time')
        suffix = ' (다음 날 종료)' if int(eh+em) < int(sh+sm) else ''
        schedule[day] = f'{sh}:{sm}–{eh}:{em}{suffix}'
    return schedule


def run(limit=None):
    observed = datetime.now(ZoneInfo('Asia/Seoul')).date()
    metadata_client = official.Client()
    client = official.Client()
    # Official hours change daily. Unlike photo metadata, never reuse a prior
    # day's response and mistake its day-of-month fields for today's dates.
    photo_cache = client.cache
    client.cache = catalog.ROOT / 'storage/official-hours-metadata' / observed.isoformat()
    client.cache.mkdir(parents=True, exist_ok=True)
    # The shipped manifest also identifies branches, so refresh works on a
    # deployment that has no local photo-research cache.
    records = dict(entries())
    stores = {row.store_id: {'s_biz_code': row.store_id, 's_name': row.branch.removeprefix('스타벅스 '),
                             'lat': row.lat, 'lot': row.lng, 'doro_address': row.address}
              for row in records.values()}
    for path in photo_cache.glob('*.json'):
        response = json.loads(path.read_text(encoding='utf-8'))
        for store in response.get('list', []) + response.get('view', []):
            if store.get('s_biz_code') and store.get('lat') and store.get('lot'):
                stores[str(store['s_biz_code'])] = store
    with catalog.connect() as con:
        places = [dict(row) for row in con.execute("SELECT * FROM places WHERE active=1 AND category='cafe'")]
    by_id = {row['id']: row for row in places}
    matched = list(official.match_branches(places, list(stores.values())).items())
    if limit is not None: matched = matched[:limit]
    failures, stopped = [], None
    success = 0
    for pid, brief in matched:
        try:
            views = metadata_client.post('getStoreView', {'in_biz_cd': str(brief['s_biz_code'])}).get('view', [])
            if (len(views) != 1 or str(views[0].get('s_biz_code')) != str(brief['s_biz_code'])
                    or not official.valid_branch(by_id[pid], official.entry_for(views[0]))):
                records.pop(pid, None)
                raise ValueError('Official branch identity no longer matches the catalog')
            brief = views[0]
            raw = client.post('getStoreTime', {'in_biz_cd': str(brief['s_biz_code']), 'in_store_type': 'C'})
            schedule = parse_schedule(raw.get('list'), observed)
            row = DatedHours(place_id=pid, **official.entry_for(brief), checked_at=observed, date_hours=schedule)
            records[pid] = row
            success += 1
        except HTTPError as error:
            failures.append({'place_id': pid, 'error': f'HTTP {error.code}'})
            if error.code in {403, 429}:
                stopped = f'Provider returned HTTP {error.code}; import stopped without retries'
                break
        except (OSError, ValueError, KeyError, TypeError) as error:
            failures.append({'place_id': pid, 'error': str(error)[:200]})
        if (success + len(failures)) % 25 == 0:
            print(f'Official hours: {success} branches, {len(failures)} unavailable / {len(matched)}', flush=True)
    # Replace atomically only after validation; failures preserve prior records.
    pending = DATA.with_suffix('.tmp')
    pending.write_text(json.dumps([r.model_dump(mode='json') for r in records.values()], ensure_ascii=False, indent=2), encoding='utf-8')
    pending.replace(DATA)
    entries.cache_clear()
    report = {'checked_at': observed.isoformat(), 'candidates': len(matched), 'updated': success,
              'recorded': len(records), 'failures': failures, 'stopped': stopped}
    (catalog.ROOT / 'artifacts/official-hours-import.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int)
    print(json.dumps(run(parser.parse_args().limit), ensure_ascii=True))
