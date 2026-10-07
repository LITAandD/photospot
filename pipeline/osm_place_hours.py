"""Display existing map hours with provenance; parse only unambiguous weeks.

Holiday, seasonal, conditional and annotated expressions retain their complete
source text. They must never be reduced to a misleading weekday time window.
"""
from datetime import date
import re
from urllib.parse import urlsplit

DAYS = ['월', '화', '수', '목', '금', '토', '일']
EN_DAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']
DAY = r'(?:Mo|Tu|We|Th|Fr|Sa|Su)'
DAY_SET = rf'{DAY}(?:-{DAY})?(?:,{DAY}(?:-{DAY})?)*'
CLOCK = r'(?:[01]\d|2[0-3]):[0-5]\d|24:00'
PERIOD = rf'(?:{CLOCK})\s*-\s*(?:{CLOCK})'
RULE = re.compile(rf'(?:(?P<days>{DAY_SET})\s+)?(?P<times>{PERIOD}(?:\s*,\s*{PERIOD})*|off|closed)', re.I)


def week_for(raw):
    if raw == '24/7': return ['24시간'] * 7
    week = [None] * 7
    for rule in raw.split(';'):
        match = RULE.fullmatch(rule.strip().replace('~', '-'))
        if not match: return None
        days = []
        for segment in (match['days'] or 'Mo-Su').split(','):
            bounds = [EN_DAYS.index(part.title()) for part in segment.split('-')]
            if len(bounds) == 1: days.append(bounds[0])
            else:
                days.extend((bounds[0] + i) % 7 for i in range((bounds[1] - bounds[0]) % 7 + 1))
        # Overlapping selectors may involve override/addition semantics. Keep
        # the complete source instead of guessing how those rules interact.
        if len(set(days)) != len(days) or any(week[day] is not None for day in days): return None
        value = match['times']
        if value.lower() in {'off', 'closed'}: rendered = '휴무'
        else:
            periods = []
            for period in value.split(','):
                start, end = [p.strip() for p in period.split('-')]
                if start == '24:00' or start == end: return None
                suffix = ' (다음 날 종료)' if end < start else ''
                periods.append(f'{start}–{end}{suffix}')
            rendered = ' / '.join(periods)
        for day in days: week[day] = rendered
    return week


def readable_source(raw):
    result = raw.replace('sunrise', '일출').replace('sunset', '일몰')
    replacements = dict(zip(EN_DAYS, DAYS)) | {'PH': '공휴일', 'SH': '방학', 'off': '휴무', 'closed': '휴무', 'open': '운영'}
    for token, label in replacements.items():
        result = re.sub(r'\b' + token + r'\b', label, result)
    return result


def hours_for(place, visit_date, today):
    raw = (place.get('opening_hours') or '').strip()
    if not raw or raw.lower() in {'unknown', 'none', '개업예정'}: return None
    url = urlsplit(place.get('source_url') or '')
    if (url.scheme != 'https' or url.hostname != 'www.openstreetmap.org' or url.username or url.password
            or url.port or not re.fullmatch(r'/(node|way|relation)/\d+', url.path)):
        return None
    try: collected = date.fromisoformat(place['fetched_at'][:10])
    except (KeyError, TypeError, ValueError): return None
    if collected > today: return None
    week = week_for(raw)
    notes = ['공개 지도에 등록된 시간이에요. 현장 운영 여부와 공휴일 변동은 출처에서 확인해 주세요.',
             '표시된 날짜는 지도 자료 수집일이며, 장소의 최종 시간표 수정일은 아니에요.']
    if week is None:
        lines = [readable_source(raw)]
        summary = '등록 운영시간 · 상세 안내 확인'
        kind = 'source_text'
        notes.append('조건이 포함된 원문을 보존했어요. 촬영일의 운영 여부는 단정하지 않아요.')
    else:
        groups = {}
        for day, value in enumerate(week):
            if value is not None: groups.setdefault(value, []).append(day)
        lines = [(('매일' if len(days) == 7 else '·'.join(DAYS[d] for d in days)) + ' ' + value)
                 for value, days in groups.items()]
        current = week[visit_date.weekday()]
        summary = f'{DAYS[visit_date.weekday()]} {current} (지도 등록)' if current else '촬영일 시간 미등록 · 상세 안내 확인'
        kind = 'regular'
        if any(value is None for value in week): notes.append('시간이 등록되지 않은 요일의 운영 여부는 출처에서 확인해 주세요.')
    stale = (today - collected).days > 30
    if stale: summary = '등록 운영시간 · 재확인 필요'
    return {'provider': 'openstreetmap', 'schedule_kind': kind, 'source_label': 'OpenStreetMap 등록시간',
            'source_url': place['source_url'], 'checked_at': collected.isoformat(), 'stale': stale,
            'summary': summary, 'weekly_hours': lines, 'notes': notes,
            'address': place.get('address') or '', 'branch_name': place['name']}
