"""Explicit, cached import of photos published on official cafe branch pages.

These are copyrighted official photos, NOT Creative Commons images. Keep their
remote URLs and attribution; never substitute another branch or a brand image.
App requests only read the resulting local catalog.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request

from . import place_catalog as catalog
from .catalog_photos import initialize, store_photos, UA

SITE = 'https://www.starbucks.co.kr'
CDN = 'https://image.istarbucks.co.kr'
METHOD = 'official:starbucks'
FLAGS = 'T03 T01 T27 T12 T09 T30 T05 T22 T21 T10 T36 T43 T48 Z9999 T64 T66 P02 P10 P50 P20 P60 P30 P70 P40 P80 whcroad_yn P90 P01 new_bool'.split()


class Client:
    def __init__(self):
        self.cache = catalog.ROOT / 'storage/official-cafe-metadata'
        self.cache.mkdir(parents=True, exist_ok=True)
        self.last = 0

    def post(self, action, params):
        url = f'{SITE}/store/{action}.do'
        body = urllib.parse.urlencode(params).encode()
        key = hashlib.sha256(url.encode() + body).hexdigest()
        path = self.cache / (key + '.json')
        if path.exists() and time.time() - path.stat().st_mtime < 7 * 86400:
            return json.loads(path.read_text(encoding='utf-8'))
        time.sleep(max(0, 1.2 - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        req = urllib.request.Request(url, data=body, headers={
            'User-Agent': UA, 'Referer': SITE + '/store/store_map.do'})
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read(15 * 1024 * 1024 + 1)
        if len(raw) > 15 * 1024 * 1024: raise ValueError('Oversized branch metadata')
        data = json.loads(raw)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return data


def branch_name(value):
    value = re.sub(r'starbucks|coffee|스타벅스|커피', '', value, flags=re.I)
    return re.sub(r'[^a-z0-9가-힣]', '', value.lower()).removesuffix('점')


def is_brand(place):
    return place.get('category') == 'cafe' and bool(re.search(r'스타벅스|starbucks', place.get('name', ''), re.I))


def road_address(value):
    match = re.search(r'([가-힣0-9·]+(?:로|길)(?:\d+번길)?)\s*(\d+(?:-\d+)?)', value or '')
    return match.groups() if match else None


def valid_branch(place, entry):
    try:
        if not is_brand(place) or catalog.distance_m(float(entry['lat']), float(entry['lng']), place) > 65:
            return False
        name = branch_name(place['name'])
        if name and name != branch_name(entry['branch']): return False
        old, new = road_address(place.get('address')), road_address(entry.get('address'))
        return not (old and new and old != new)
    except (KeyError, TypeError, ValueError):
        return False


def entry_for(store):
    return {'store_id': str(store['s_biz_code']), 'branch': '스타벅스 ' + store['s_name'],
            'lat': float(store['lat']), 'lng': float(store['lot']),
            'address': store.get('doro_address') or store.get('addr') or ''}


def match_branches(places, stores):
    stores = [s for s in stores if s.get('s_biz_code') and s.get('lat') and s.get('lot') and s.get('hlytag') != '4']
    candidates = []
    for place in places:
        if not is_brand(place): continue
        nearest = sorted((catalog.distance_m(float(s['lat']), float(s['lot']), place), i) for i, s in enumerate(stores))
        if not nearest or nearest[0][0] > 65: continue
        distance, index = nearest[0]
        store = stores[index]
        if not valid_branch(place, entry_for(store)): continue
        # A generic brand name is insufficient in a mall or a dense cluster.
        if not branch_name(place['name']) and (distance > 50 or len(nearest) > 1 and nearest[1][0] < max(90, distance + 50)):
            continue
        candidates.append((distance, place['id'], store))
    used, result = set(), {}
    for _, pid, store in sorted(candidates, key=lambda row: (row[0], row[1])):
        if store['s_biz_code'] in used: continue
        used.add(store['s_biz_code'])
        result[pid] = store
    return result


def image_urls(store):
    result = []
    for path in [store.get('defaultimage') or '', *(store.get('etcimage') or '').split(',')]:
        path = path.strip()
        if not re.fullmatch(r'/upload/store/[\w/\[\](). -]+\.(?:jpg|jpeg|png|webp)', path, flags=re.I): continue
        if any(part in {'.', '..'} for part in path.split('/')): continue
        # Paths must identify this branch; shared logos/placeholders are not photos.
        code = re.escape(str(store['s_biz_code']))
        if not re.search(r'/\[?' + code + r'\]?_', path): continue
        url = CDN + urllib.parse.quote(path, safe='/')
        if url not in result: result.append(url)
    return result


def records_for(pid, store):
    entry = entry_for(store)
    source = SITE + '/store/store_map.do?in_biz_cd=' + entry['store_id']
    return [{'place_id': pid, 'file_title': entry['branch'] + ' · 공식 사진 ' + hashlib.sha256(url.encode()).hexdigest()[:12],
             'url': url, 'original_url': url, 'source_url': source,
             'license': '© Starbucks Korea', 'license_url': '', 'attribution': entry['branch'] + ' · 공식 매장 사진',
             'description': entry['address'], 'width': 0, 'height': 0,
             'match_method': METHOD, 'match_ref': json.dumps(entry, ensure_ascii=False),
             'priority': 5 if index == 0 else 20 + index}
            for index, url in enumerate(image_urls(store))]


def enrich_places(places, path=None):
    """Use verified branch names/addresses without modifying the OSM source rows."""
    by_id = {p['id']: p for p in places}
    if not by_id: return places
    with catalog.connect(path) as conn:
        initialize(conn)
        for start in range(0, len(by_id), 400):
            ids = list(by_id)[start:start+400]
            rows = conn.execute(f"SELECT DISTINCT place_id,match_ref FROM catalog_photos WHERE match_method=? AND place_id IN ({','.join('?' for _ in ids)})", [METHOD, *ids])
            for row in rows:
                entry = json.loads(row['match_ref'])
                place = by_id[row['place_id']]
                if valid_branch(place, entry):
                    place['name'] = entry['branch']
                    place['address'] = entry['address'] or place.get('address')
    return places


def run(client=None, limit=None):
    client = client or Client()
    regions = client.post('getSidoList', {})['list']
    # These provinces intersect the four areas currently in the place catalog.
    selected = [r['sido_cd'] for r in regions if r['sido_nm'] in {'서울', '경기', '부산', '제주', '강원'}]
    stores = {}
    for region in selected:
        params = {key: '0' for key in FLAGS}
        params.update({'ins_lat': '37.5665', 'ins_lng': '126.9780', 'p_sido_cd': region,
                       'p_gugun_cd': '', 'in_distance': '0', 'in_biz_cd': '', 'in_biz_cds': '0',
                       'in_scodes': '0', 'set_date': '', 'iend': '1000', 'search_text': '',
                       'searchType': 'C', 'isError': 'true', 'all_store': '0'})
        batch = client.post('getStore', params)['list']
        if not batch: raise ValueError('Empty regional response; existing photos retained')
        stores.update({str(s['s_biz_code']): s for s in batch})
        print(f'Region {region}: {len(batch)} public branch records', flush=True)
    with catalog.connect() as conn:
        places = [dict(r) for r in conn.execute("SELECT * FROM places WHERE active=1 AND category='cafe'")]
    by_id = {p['id']: p for p in places}
    matches = list(match_branches(places, list(stores.values())).items())[:limit]
    audit, failures = [], []
    for index, (pid, brief) in enumerate(matches, 1):
        try:
            rows = client.post('getStoreView', {'in_biz_cd': str(brief['s_biz_code'])}).get('view', [])
            if len(rows) != 1 or str(rows[0].get('s_biz_code')) != str(brief['s_biz_code']):
                raise ValueError('Branch identity changed')
            store = rows[0]
            if store.get('hlytag') == '4' or not valid_branch(by_id[pid], entry_for(store)):
                raise ValueError('Branch identity no longer agrees')
            records = records_for(pid, store)
            if not records: raise ValueError('No branch-specific images')
            store_photos(records)
            with catalog.connect() as conn:
                # Refresh only this provider after a complete successful branch response.
                titles = [r['file_title'] for r in records]
                conn.execute(f"DELETE FROM catalog_photos WHERE place_id=? AND match_method=? AND file_title NOT IN ({','.join('?' for _ in titles)})", [pid, METHOD, *titles])
            audit.append({'place_id': pid, **entry_for(store), 'photos': len(records), 'source_url': records[0]['source_url']})
        except (OSError, ValueError, KeyError, TypeError) as error:
            failures.append({'place_id': pid, 'error': type(error).__name__ + ': ' + str(error)})
        if index % 20 == 0 or index == len(matches):
            print(f'Branches {index}/{len(matches)}; linked {len(audit)}; photos {sum(r["photos"] for r in audit)}; unavailable {len(failures)}', flush=True)
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'provider': METHOD,
              'places': len(audit), 'photos': sum(r['photos'] for r in audit), 'branches': audit, 'failures': failures}
    (catalog.ROOT / 'artifacts/cafe-official-photo-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return {k: report[k] for k in ('places', 'photos')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int)
    print(json.dumps(run(limit=parser.parse_args().limit)))
