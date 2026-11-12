"""Sourced public visit facts. Never infer venue setting/time/fees from its category."""
from datetime import date
from functools import lru_cache
import json
from pathlib import Path
from urllib.parse import urlsplit

from pipeline.catalog_visitors import today
from pipeline.catalog_visuals import REVIEWS

# Coordinates match the existing starting-place presets, not an invented GPS location.
ORIGINS = {
    'seoul': {'city': 'seoul', 'label': '서울 종로·북촌', 'lat': 37.5796, 'lng': 126.977},
    'busan': {'city': 'busan', 'label': '부산 해운대·미포', 'lat': 35.1587, 'lng': 129.1604},
    'gangneung': {'city': 'gangneung', 'label': '강릉 경포·초당', 'lat': 37.7953, 'lng': 128.9090},
    'jeju': {'city': 'jeju', 'label': '제주 제주시', 'lat': 33.4996, 'lng': 126.5312},
}
DATA = Path(__file__).resolve().parents[1] / 'pipeline/data/public_place_info.json'
KINDS = {'setting', 'background', 'photo_point', 'recommended_time', 'admission', 'reservation'}
HOSTS = {'royal.khs.go.kr', 'www.gogung.go.kr', 'korean.visitseoul.net'}


@lru_cache(maxsize=1)
def reviewed():
    return json.loads(DATA.read_text(encoding='utf-8'))


def facts_for(place_id, evidence=None, cover=None, *, on=None):
    current = on or today()
    facts = []
    for fact in reviewed().get(place_id, []):
        parsed = urlsplit(fact['source_url'])
        age = (current - date.fromisoformat(fact['checked_at'])).days
        if (fact['kind'] in KINDS and parsed.scheme == 'https' and parsed.hostname in HOSTS
                and not parsed.username and parsed.port in (None, 443) and 0 <= age <= fact.get('valid_days', 30)):
            facts.append({k: v for k, v in fact.items() if k != 'valid_days'})
    # A reviewed observation describes only the exact cover, not the whole venue.
    review = REVIEWS.get(place_id)
    if (evidence and cover and review and review['scene_usable'] and
            (review['photo_url'], review['source_url']) == (evidence['photo_url'], evidence['source_url']) == (cover['url'], cover.get('source_url'))):
        attrs = evidence.get('attributes', {})
        labels = {'linear': '직선적인 구조', 'curved': '곡선이 있는 구조', 'organic': '자연스러운 형태', 'volumetric': '입체적인 구조'}
        if attrs.get('form') in labels and attrs['form'] == review['form']:
            facts.append({'kind': 'background', 'label': '대표사진 배경', 'value': labels[attrs['form']],
                          'source_label': '해당 대표사진 형태 검토', 'source_url': cover['source_url'],
                          'checked_at': review['checked_at']})
    return facts
