"""Link place-specific, reusable Commons images to the local catalog.

No name-only search, brand photos, or guessed licenses. Network work is an explicit
CLI operation; app requests only read SQLite. Successful responses are cached so
interrupted imports can resume without repeating provider requests.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
from http.client import IncompleteRead
import json
import math
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request
import urllib.error

from . import place_catalog as catalog
from .place_categories import GROUPS

COMMONS = 'https://commons.wikimedia.org/w/api.php'
WIKIDATA = 'https://www.wikidata.org/w/api.php'
MEDIA_KEYS = {'image', 'wikimedia_commons', 'wikidata', 'wikipedia'}
CACHE = catalog.ROOT / 'storage' / 'photo-metadata'
UA = 'PhotoSpot/1.0 (local place-photo catalog; read-only metadata import)'


def initialize(conn):
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS catalog_photos (
            place_id TEXT NOT NULL, file_title TEXT NOT NULL, url TEXT NOT NULL,
            original_url TEXT NOT NULL, source_url TEXT NOT NULL, license TEXT NOT NULL,
            license_url TEXT NOT NULL, attribution TEXT NOT NULL, description TEXT,
            width INTEGER NOT NULL, height INTEGER NOT NULL, match_method TEXT NOT NULL,
            match_ref TEXT NOT NULL, priority INTEGER NOT NULL, fetched_at TEXT NOT NULL,
            PRIMARY KEY(place_id, file_title));
        CREATE INDEX IF NOT EXISTS catalog_photo_place ON catalog_photos(place_id, priority);
        CREATE TABLE IF NOT EXISTS photo_imports (stage TEXT PRIMARY KEY, completed_at TEXT NOT NULL, count INTEGER NOT NULL);
    ''')


class PublicClient:
    def __init__(self, cache=CACHE):
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.last_request = 0

    def get(self, endpoint, params=None):
        params = params or {}
        url = endpoint + ('?' + urllib.parse.urlencode(params) if params else '')
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.cache / (key + '.json')
        if path.exists() and time.time() - path.stat().st_mtime < 7 * 86400:
            return json.loads(path.read_text(encoding='utf-8'))
        wait = 6.2 - (time.monotonic() - self.last_request)
        if wait > 0: time.sleep(wait)
        req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
        for attempt in range(3):
            self.last_request = time.monotonic()
            try:
                with urllib.request.urlopen(req, timeout=55) as response:
                    data = response.read(30 * 1024 * 1024 + 1)
                if len(data) > 30 * 1024 * 1024: raise ValueError('Metadata response too large')
                raw = json.loads(data)
                error = raw.get('error') or ({'code': 'partial', 'info': raw['remark']} if raw.get('remark') else None)
                if not error: break
                if error.get('code') != 'maxlag' or attempt == 2:
                    raise ValueError(f"Provider error {error.get('code')}: {error.get('info')}")
                delay = 30 * (attempt + 1)
            except urllib.error.HTTPError as error:
                if error.code not in {429, 502, 503, 504} or attempt == 2: raise
                retry = error.headers.get('Retry-After', '')
                delay = max(5, int(retry)) if retry.isdigit() else 60 * (attempt + 1)
                if delay > 300: raise
            except (TimeoutError, urllib.error.URLError, IncompleteRead):
                if attempt == 2: raise
                delay = 30 * (attempt + 1)
            print(f'Provider busy; retrying after {delay}s ({attempt+1}/2)', flush=True)
            time.sleep(delay)
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding='utf-8')
        return raw


def media_query(region):
    lat, lng, radius = catalog.REGIONS[region]
    dy, dx = radius / 111000, radius / (111000 * math.cos(math.radians(lat)))
    box = f'({lat-dy:.6f},{lng-dx:.6f},{lat+dy:.6f},{lng+dx:.6f})'
    return '[out:json][timeout:35];nwr[~"^(image|wikimedia_commons|wikidata|wikipedia)$"~"."]' + box + ';out tags;'


def import_references(raw, path=None):
    if raw.get('remark') or not isinstance(raw.get('elements'), list):
        raise ValueError('Incomplete media references; catalog retained')
    changed = 0
    with catalog.connect(path) as conn:
        for element in raw['elements']:
            row = conn.execute('SELECT id,tags FROM places WHERE osm_type=? AND osm_id=? AND active=1',
                               (element.get('type'), element.get('id'))).fetchone()
            if not row: continue
            refs = {k: v for k, v in (element.get('tags') or {}).items() if k in MEDIA_KEYS and isinstance(v, str)}
            if not refs: continue
            tags = json.loads(row['tags'])
            tags.update(refs)
            conn.execute('UPDATE places SET tags=? WHERE id=?', (json.dumps(tags, ensure_ascii=False), row['id']))
            changed += 1
    return changed


def scan(client, regions):
    for index, region in enumerate(regions):
        if index: time.sleep(30)  # Respect the shared public Overpass service.
        raw = client.get(catalog.ENDPOINT, {'data': media_query(region)})
        count = import_references(raw)
        with catalog.connect() as conn:
            initialize(conn)
            conn.execute('INSERT OR REPLACE INTO photo_imports VALUES (?,?,?)',
                         ('references:' + region, datetime.now(timezone.utc).isoformat(), count))
        print(f'{region}: {count} existing places have media references', flush=True)


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
    def handle_data(self, data): self.parts.append(data)


def plain(value):
    parser = PlainText()
    parser.feed(str(value or ''))
    return ' '.join(' '.join(parser.parts).split())


def https_url(value, hosts):
    value = str(value or '').strip()
    if value.startswith('//'): value = 'https:' + value
    try:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in {'http', 'https'} or parsed.hostname not in hosts or parsed.username or parsed.password or parsed.port not in {None, 80, 443}:
            return None
    except ValueError: return None
    return urllib.parse.urlunsplit(('https', parsed.netloc, parsed.path, parsed.query, ''))


def commons_title(value):
    value = str(value or '').strip()
    if value.startswith(('http://', 'https://')):
        url = urllib.parse.urlsplit(value)
        if url.hostname == 'commons.wikimedia.org' and url.path.startswith('/wiki/'):
            value = urllib.parse.unquote(url.path[6:])
        elif url.hostname == 'upload.wikimedia.org' and '/wikipedia/commons/' in url.path:
            parts = urllib.parse.unquote(url.path).split('/')
            value = 'File:' + (parts[-2] if '/thumb/' in url.path else parts[-1])
        else: return None
    value = value.replace('_', ' ')
    if not value.startswith(('File:', 'Category:')): return None
    prefix, name = value.split(':', 1)
    name = name.strip()
    if not name or any(c in name for c in ['|', '\n', '\r']): return None
    return prefix + ':' + name[0].upper() + name[1:]


def reusable_image(page):
    """Return only API-verified raster images with an explicit reusable license."""
    if not page.get('imageinfo'): return None
    info = page['imageinfo'][0]
    if info.get('mime') not in {'image/jpeg', 'image/png', 'image/webp'}: return None
    if min(info.get('width', 0), info.get('height', 0)) < 100: return None
    meta = {k: plain(v.get('value')) for k, v in info.get('extmetadata', {}).items()}
    license_name = meta.get('LicenseShortName', '')
    license_url = https_url(meta.get('LicenseUrl'), {'creativecommons.org', 'www.gnu.org'})
    if license_url and re.search(r'^https://creativecommons.org/licenses/by(?:-sa)?/\d\.\d(?:/|$)', license_url):
        pass
    elif license_url and license_url.startswith('https://creativecommons.org/publicdomain/'):
        pass
    elif license_name.lower() == 'public domain':
        license_url = 'https://creativecommons.org/publicdomain/mark/1.0/'
    elif license_name.startswith('GFDL') and license_url and license_url.startswith('https://www.gnu.org/licenses/'):
        pass
    else: return None
    artist = meta.get('Attribution') or meta.get('Artist')
    if not artist or not license_name: return None
    url = https_url(info.get('thumburl') or info.get('url'), {'upload.wikimedia.org', 'thumb.wikimedia.org'})
    original = https_url(info.get('url'), {'upload.wikimedia.org'})
    source = https_url(info.get('descriptionurl'), {'commons.wikimedia.org'})
    if not url or not original or not source: return None
    return {'file_title': page['title'], 'url': url, 'original_url': original, 'source_url': source,
            'license': license_name, 'license_url': license_url, 'attribution': artist,
            'description': meta.get('ImageDescription', ''), 'width': info['width'], 'height': info['height']}


def chunks(values, size=40):
    batch, length = [], 0
    for value in values:
        encoded = len(urllib.parse.quote(value))
        if batch and (len(batch) >= size or length + encoded > 6500):
            yield batch
            batch, length = [], 0
        batch.append(value)
        length += encoded + 3
    if batch: yield batch


def claims(entity, prop):
    return [row['mainsnak']['datavalue']['value'] for row in entity.get('claims', {}).get(prop, [])
            if row.get('rank') != 'deprecated' and row.get('mainsnak', {}).get('snaktype') == 'value' and row['mainsnak'].get('datavalue')]


BRAND_ENTITIES = {'Q37158', 'Q12611298', 'Q120998343'}  # Starbucks, Ediya, Mega: not a branch.


def nearby_entity(entity, place):
    coordinates = claims(entity, 'P625')
    if place['category'] in GROUPS['cafe']:
        if entity.get('id') in BRAND_ENTITIES or not coordinates: return False
        return any(catalog.distance_m(place['lat'], place['lng'], {'lat': p['latitude'], 'lng': p['longitude']}) <= 150
                   for p in coordinates if p.get('globe', '').endswith('/Q2'))
    # Exclude a parent institution whose mapped location differs from this branch.
    if not coordinates: return True  # The explicit OSM/Wikipedia link still provides identity.
    limit = 15000 if place['category'] in {'scenic', 'waterfront'} else 2500
    return any(catalog.distance_m(place['lat'], place['lng'], {'lat': p['latitude'], 'lng': p['longitude']}) <= limit
               for p in coordinates if p.get('globe', '').endswith('/Q2'))


def candidates(client, places, include_categories=True):
    from .place_editorial import editorial
    from .cafe_photos import matches as cafe_matches, files_for
    files, categories = defaultdict(dict), defaultdict(dict)
    by_id, by_wiki = defaultdict(list), defaultdict(lambda: defaultdict(list))
    def add(target, title, place_id, method, reference, priority):
        previous = target[title].get(place_id)
        if previous is None or priority < previous[2]: target[title][place_id] = (method, reference, priority)
    active_ids = {place['id'] for place in places}
    for pid, entry in cafe_matches(places).items():
        for index, title in enumerate(files_for(entry)):
            add(files, title, pid, 'reviewed:branch', entry['verified_by'], 1 if index == 0 else 30 + index)
    for entry in editorial().get('commons_photos', []):
        if entry['place_id'] in active_ids:
            for title in entry['files']:
                add(files, title, entry['place_id'], 'curated:commons', title, 5)
    for place in places:
        tags = json.loads(place['tags'])
        for key in ['image', 'wikimedia_commons']:
            title = commons_title(tags.get(key))
            if title:
                add(categories if title.startswith('Category:') else files, title, place['id'], 'osm:' + key, tags[key], 30 if title.startswith('Category:') else 0)
        ids = [q.strip() for q in tags.get('wikidata', '').split(';') if re.fullmatch(r'Q[1-9]\d*', q.strip())]
        for qid in ids: by_id[qid].append(place)
        wiki = tags.get('wikipedia', '').partition(':')
        if not ids and re.fullmatch(r'[a-z][a-z-]{1,11}', wiki[0]) and wiki[2]: by_wiki[wiki[0]][wiki[2]].append(place)

    def entity_files(entity, matches, reference):
        for place in matches:
            if place['category'] in GROUPS['cafe'] and reference in BRAND_ENTITIES: continue
            if not nearby_entity(entity, place): continue
            for prop, priority in [('P18', 10), ('P5775', 15), ('P1766', 20)]:
                for value in claims(entity, prop):
                    title = commons_title('File:' + value) if isinstance(value, str) else None
                    if title: add(files, title, place['id'], 'wikidata:' + prop, reference, priority)
            for value in claims(entity, 'P373'):
                title = commons_title('Category:' + value) if isinstance(value, str) else None
                if title: add(categories, title, place['id'], 'wikidata:P373', reference, 40)

    for batch in chunks(by_id):
        raw = client.get(WIKIDATA, {'action': 'wbgetentities', 'ids': '|'.join(batch), 'props': 'claims', 'format': 'json', 'maxlag': 5})
        for qid, entity in raw.get('entities', {}).items(): entity_files(entity, by_id[qid], qid)
    for language, titles in by_wiki.items():
        for batch in chunks(titles):
            raw = client.get(WIKIDATA, {'action': 'wbgetentities', 'sites': language + 'wiki', 'titles': '|'.join(batch),
                                      'props': 'claims|sitelinks', 'format': 'json', 'maxlag': 5})
            for qid, entity in raw.get('entities', {}).items():
                title = entity.get('sitelinks', {}).get(language + 'wiki', {}).get('title')
                entity_files(entity, titles.get(title, []), qid)
    print(f'Matched {len(files)} direct files and {len(categories)} place-specific categories', flush=True)
    if not include_categories: return files
    for index, (category, matches) in enumerate(categories.items(), 1):
        continuation = {}
        while True:
            raw = client.get(COMMONS, {'action': 'query', 'list': 'categorymembers', 'cmtitle': category,
                                      'cmtype': 'file', 'cmlimit': 500, 'format': 'json', 'maxlag': 5, **continuation})
            for item in raw.get('query', {}).get('categorymembers', []):
                title = commons_title(item.get('title'))
                if title:
                    for pid, (method, reference, priority) in matches.items():
                        add(files, title, pid, method, category, priority)
            continuation = raw.get('continue')
            if not continuation: break
        if index % 10 == 0: print(f'Categories {index}/{len(categories)}; {len(files)} candidate files', flush=True)
    return files


def store_photos(records, path=None):
    now = datetime.now(timezone.utc).isoformat()
    with catalog.connect(path) as conn:
        initialize(conn)
        for record in records:
            conn.execute('''INSERT INTO catalog_photos VALUES
                (:place_id,:file_title,:url,:original_url,:source_url,:license,:license_url,:attribution,:description,
                 :width,:height,:match_method,:match_ref,:priority,:fetched_at)
                ON CONFLICT(place_id,file_title) DO UPDATE SET url=excluded.url, original_url=excluded.original_url,
                source_url=excluded.source_url, license=excluded.license, license_url=excluded.license_url,
                attribution=excluded.attribution, description=excluded.description, width=excluded.width,
                height=excluded.height, match_method=excluded.match_method, match_ref=excluded.match_ref,
                priority=excluded.priority, fetched_at=excluded.fetched_at''', {**record, 'fetched_at': now})


def import_files(client, files):
    linked, rejected = 0, 0
    accepted = set()
    batches = list(chunks(files, 40))
    for index, batch in enumerate(batches, 1):
        raw = client.get(COMMONS, {'action': 'query', 'titles': '|'.join(batch), 'redirects': 1, 'prop': 'imageinfo',
                                  'iiprop': 'url|extmetadata|mime|size', 'iiurlwidth': 960, 'format': 'json', 'maxlag': 5})
        query = raw.get('query', {})
        aliases = {entry['from']: entry['to'] for key in ['normalized', 'redirects'] for entry in query.get(key, [])}
        mapped = defaultdict(dict)
        for title in batch:
            canonical, seen = title, set()
            while canonical in aliases and canonical not in seen:
                seen.add(canonical)
                canonical = aliases[canonical]
            for pid, match in files[title].items():
                previous = mapped[canonical].get(pid)
                if previous is None or match[2] < previous[2]: mapped[canonical][pid] = match
        records = []
        for page in query.get('pages', {}).values():
            photo = reusable_image(page)
            if not photo:
                rejected += 1
                continue
            for pid, (method, reference, priority) in mapped.get(page['title'], {}).items():
                records.append({**photo, 'place_id': pid, 'match_method': method, 'match_ref': reference, 'priority': priority})
                accepted.add((pid, photo['file_title']))
        store_photos(records)
        linked += len(records)
        print(f'Image batch {index}/{len(batches)}: {linked} links; {rejected} unavailable/non-reusable files', flush=True)
    return accepted


def prune_completed_links(place_ids, accepted, path=None):
    """Only a fully successful refresh removes files no longer linked/licensed."""
    with catalog.connect(path) as conn:
        initialize(conn)
        conn.execute('CREATE TEMP TABLE refreshed_places (id TEXT PRIMARY KEY)')
        conn.executemany('INSERT INTO refreshed_places VALUES (?)', [(pid,) for pid in place_ids])
        conn.execute('CREATE TEMP TABLE accepted_photos (place_id TEXT, file_title TEXT, PRIMARY KEY(place_id,file_title))')
        conn.executemany('INSERT INTO accepted_photos VALUES (?,?)', accepted)
        conn.execute('''DELETE FROM catalog_photos WHERE place_id IN (SELECT id FROM refreshed_places)
            AND match_method NOT LIKE 'official:%'
            AND match_method != 'licensed:naver'
            AND NOT EXISTS (SELECT 1 FROM accepted_photos a WHERE a.place_id=catalog_photos.place_id AND a.file_title=catalog_photos.file_title)''')


def link(client, direct_only=False):
    with catalog.connect() as conn:
        initialize(conn)
        places = [dict(r) for r in conn.execute('SELECT * FROM places WHERE active=1')]
    # Save representative photos first, then collect the remaining category photos.
    direct = candidates(client, places, include_categories=False)
    accepted = import_files(client, direct)
    if not direct_only:
        files = candidates(client, places)
        files = {title: {pid: match for pid, match in matches.items() if pid not in direct.get(title, {})}
                 for title, matches in files.items()}
        files = {title: matches for title, matches in files.items() if matches}
        accepted.update(import_files(client, files))
        prune_completed_links([p['id'] for p in places], accepted)
    with catalog.connect() as conn:
        conn.execute('INSERT OR REPLACE INTO photo_imports VALUES (?,?,?)', ('commons:direct' if direct_only else 'commons', datetime.now(timezone.utc).isoformat(), len(accepted)))
    print(json.dumps(summary(), ensure_ascii=True), flush=True)


def summary(path=None):
    with catalog.connect(path) as conn:
        initialize(conn)
        return dict(conn.execute('''SELECT count(*) photo_links, count(DISTINCT file_title) unique_files,
            count(DISTINCT place_id) places_with_photos FROM catalog_photos cp JOIN places p ON p.id=cp.place_id WHERE p.active=1''').fetchone())


def branch_photo(row):
    if row['match_method'] == 'licensed:naver':
        from .naver_photos import valid_branch
        try:
            return valid_branch(dict(row), json.loads(row['match_ref']))
        except (ValueError, TypeError):
            return False
    if row['match_method'] == 'official:starbucks':
        from .official_cafe_photos import valid_branch
        try:
            return valid_branch(dict(row), json.loads(row['match_ref']))
        except (ValueError, TypeError):
            return False
    # Older imports attached chain-wide galleries through brand Wikidata tags.
    # Keep direct branch photo references; exclude brand-derived galleries everywhere.
    return not (row['category'] in GROUPS['cafe'] and row['match_method'].startswith('wikidata:') and
                set(json.loads(row['tags']).get('wikidata', '').split(';')) & BRAND_ENTITIES)


def photo_counts_for(ids, path=None):
    from .place_editorial import official_photos_for
    ids = list(ids)
    result = {pid: len(photos) for pid, photos in official_photos_for(ids).items() if photos}
    if not ids: return result
    with catalog.connect(path) as conn:
        initialize(conn)
        for start in range(0, len(ids), 400):
            batch = ids[start:start + 400]
            for row in conn.execute(f'''SELECT cp.place_id,cp.match_method,cp.match_ref,p.category,p.tags,p.name,p.address,p.lat,p.lng FROM catalog_photos cp
                JOIN places p ON p.id=cp.place_id WHERE cp.place_id IN ({','.join('?' for _ in batch)})''', batch):
                if branch_photo(row): result[row['place_id']] = result.get(row['place_id'], 0) + 1
    return result


def photos_for(ids, path=None):
    from .place_editorial import official_photos_for
    ids = list(ids)
    if not ids: return {}
    with catalog.connect(path) as conn:
        initialize(conn)
        rows = conn.execute(f'''SELECT cp.*,p.category,p.tags,p.name,p.address,p.lat,p.lng FROM catalog_photos cp JOIN places p ON p.id=cp.place_id
                              WHERE cp.place_id IN ({','.join('?' for _ in ids)})
                              ORDER BY priority,file_title''', ids).fetchall()
    result = defaultdict(list, official_photos_for(ids))
    for row in rows:
        if not branch_photo(row): continue
        title = (row['description'] if row['match_method'] == 'licensed:naver' else json.loads(row['match_ref'])['branch'] + ' · 공식 매장 사진'
                 if row['match_method'] == 'official:starbucks' else row['file_title'].removeprefix('File:'))
        result[row['place_id']].append({'url': row['url'], 'attribution': row['attribution'], 'license': row['license'],
            'keep_aspect_ratio': True, 'source_url': row['source_url'], 'license_url': row['license_url'],
            'original_url': row['original_url'], 'title': title,
            'width': row['width'], 'height': row['height']})
    return dict(result)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--scan', action='store_true')
    ap.add_argument('--link', action='store_true')
    ap.add_argument('--direct-only', action='store_true', help='Only representative files; the normal import includes category images too')
    ap.add_argument('--regions', default=','.join(catalog.REGIONS))
    args = ap.parse_args()
    regions = args.regions.split(',')
    if any(region not in catalog.REGIONS for region in regions): ap.error('Unknown region')
    client = PublicClient()
    if args.scan: scan(client, regions)
    if args.link: link(client, direct_only=args.direct_only)


if __name__ == '__main__': main()
