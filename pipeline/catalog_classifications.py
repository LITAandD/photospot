"""Exact-place, source-reviewed service categories; not a psychological finding."""
from functools import lru_cache
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from .catalog_visitors import today

DATA = Path(__file__).with_name('data') / 'place_classifications.json'


@lru_cache(maxsize=1)
def records():
    return {r['place_id']: r for r in json.loads(DATA.read_text(encoding='utf-8'))}


def classification_for(place):
    from .catalog_mbti import official_source
    row = records().get(place.get('id'))
    if not row:
        return None
    try:
        if (row['place_name'] != place.get('name') or row['place_source'] != place.get('source_url')
                or abs(row['lat'] - place['lat']) > .0001 or abs(row['lng'] - place['lng']) > .0001
                or row['value'] not in {'architecture', 'nature', 'mixed'}
                or not official_source(urlsplit(row['source_url']))
                or not 0 <= (today() - date.fromisoformat(row['checked_at'])).days <= 365
                or not row['excerpt'].strip() or not row['rationale'].strip()):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    labels = {'architecture': '건축물 중심', 'nature': '자연물 중심', 'mixed': '건축물·자연물 혼합'}
    return row['value'], '출처 대조 후 서비스 분류: ' + labels[row['value']] + ' · ' + row['rationale'], [
        {'url': row['source_url'], 'label': row['label'], 'excerpt': row['excerpt'], 'checked_at': row['checked_at']}]
