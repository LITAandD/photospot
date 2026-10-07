"""Source-backed cultural interpretations, separate from photographic analysis.

Exact place interpretations take precedence over regional ones. Source facts and
our landscape/material interpretations are explicitly distinguished in the UI.
No network requests or guessed classifications occur during app requests.
"""
from functools import lru_cache
import json
from pathlib import Path

from .place_catalog import distance_m

DATA = Path(__file__).parent / 'data'
ORDER = ['wood', 'fire', 'earth', 'metal', 'water']
LABELS = dict(zip(ORDER, ['목(木)', '화(火)', '토(土)', '금(金)', '수(水)']))


@lru_cache(maxsize=1)
def editorial():
    return json.loads((DATA / 'place_editorial.json').read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def regions():
    return json.loads((DATA / 'jamsil_boundaries.json').read_text(encoding='utf-8'))['regions']


def in_ring(lat, lng, ring):
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > lat) != (y2 > lat) and lng < (x2-x1) * (lat-y1) / (y2-y1) + x1:
            inside = not inside
    return inside


def region_for(place):
    if 'lat' not in place or 'lng' not in place: return None
    lat, lng = place['lat'], place['lng']
    for region in regions():
        west, south, east, north = region['bbox']
        if not (west <= lng <= east and south <= lat <= north): continue
        if any(in_ring(lat, lng, ring) for ring in region['outer']) and not any(in_ring(lat, lng, ring) for ring in region['inner']):
            return region
    return None


def profile(elements, basis, label, explanation, sources):
    return {'elements': [e for e in ORDER if e in elements], 'basis': basis, 'label': label,
            'explanation': explanation, 'sources': sources, 'checked_at': editorial()['checked_at']}


def resolve_elements(place):
    data = editorial()
    sources = data['sources']
    name = ''.join(place.get('name', '').split()).lower()
    for rule in data['places']:
        if name not in {''.join(n.split()).lower() for n in rule['names']}: continue
        if 'lat' not in place or 'lng' not in place: continue
        if distance_m(place['lat'], place['lng'], {'lat': rule['center'][0], 'lng': rule['center'][1]}) > rule['radius_m']: continue
        return profile(rule['elements'], rule['basis'], rule['label'], rule['explanation'], [sources[s] for s in rule['sources']])
    region = region_for(place)
    if region:
        return profile(['water'], 'regional', f"{region['name']} · 수(水)",
            '옛 잠실섬과 한강 물길의 지역사를 바탕으로 수를 적용해요. 지역 지형을 선택한 참고 해석이며 개별 건물의 풍수 판정은 아니에요.',
            [sources['jamsil'], sources['elements'], {'title': f"OpenStreetMap · {region['name']} 경계", 'url': region['source_url']}])
    tags = json.loads(place.get('tags', '{}'))
    elements, observations = set(), []
    if place.get('category') == 'park':
        elements.add('wood'); observations.append('지도에 등록된 공원·정원')
    if place.get('category') == 'waterfront' or tags.get('waterway') == 'waterfall':
        elements.add('water'); observations.append('지도에 등록된 수변·폭포')
    if tags.get('material') in {'steel', 'metal', 'iron'}:
        elements.add('metal'); observations.append('등록된 금속 소재')
    if tags.get('material') in {'stone', 'brick', 'earth'} or tags.get('natural') in {'rock', 'stone'}:
        elements.add('earth'); observations.append('등록된 흙·돌 소재')
    if tags.get('material') in {'wood', 'timber'}:
        elements.add('wood'); observations.append('등록된 목재 소재')
    if elements:
        refs = [sources['elements']]
        if place.get('source_url'): refs.append({'title': 'OpenStreetMap · 이 장소의 지형·소재', 'url': place['source_url']})
        return profile(elements, 'landscape', '·'.join(LABELS[e] for e in ORDER if e in elements),
            '·'.join(observations) + '을 오행의 자연·소재 상징에 대응한 해석이에요. 이 장소를 직접 논한 풍수 문헌은 아직 확인하지 못했어요.', refs)
    return profile([], 'unassigned', '오행 근거 확인 전',
        '현재 확인한 자료에는 이 장소의 오행을 지정할 근거가 충분하지 않아요.', [])


def official_photos_for(ids):
    wanted, result = set(ids), {}
    for entry in editorial()['official_photos']:
        if entry['place_id'] not in wanted: continue
        result[entry['place_id']] = [
            {'url': entry['base_url'] + name, 'original_url': entry['base_url'] + name,
             'source_url': entry['source_url'], 'license_url': None, 'license': entry['license'],
             'attribution': entry['attribution'], 'keep_aspect_ratio': True,
             'title': f"{entry['place_name']} · 공식 사진 {i + 1}"}
            for i, name in enumerate(entry['files'])]
    return result
