"""Reviewed dining branches and a persistent Starbucks allowlist.

Public articles are qualitative selection evidence, never Instagram post counts
or visitor statistics. Refreshes use exact OSM identities, not chain-wide names.
"""
from functools import lru_cache
import json
from pathlib import Path
import re

MANIFEST = Path(__file__).parent / 'data/dining_curation.json'


@lru_cache(maxsize=1)
def entries():
    rows = json.loads(MANIFEST.read_text(encoding='utf-8'))['places']
    result = {r['source_url']: r for r in rows}
    if len(result) != len(rows):
        raise ValueError('Duplicate curated dining branch')
    return result


def is_starbucks(name, tags):
    return (tags.get('brand:wikidata') == 'Q37158' or
            bool(re.search(r'스타\s*벅스|star\s*bucks', ' '.join(str(tags.get(k, '')) for k in
                 ('name', 'name:ko', 'name:en', 'brand', 'brand:en')) + ' ' + name, re.I)))


def excluded_starbucks(name, tags, source_url):
    return is_starbucks(name, tags) and not entries().get(source_url, {}).get('starbucks_keep', False)


def category_override(name, source_url):
    entry = entries().get(source_url)
    return entry['category'] if entry and name in entry['names'] else None


def match(place):
    from .place_catalog import distance_m
    entry = entries().get(place.get('source_url', ''))
    if not entry or distance_m(entry['lat'], entry['lng'], place) > 75:
        return None
    if place['name'] not in entry['names'] and place['name'] != entry['display_name']:
        return None
    return entry


def evidence(place):
    entry = match(place)
    if not entry:
        return None
    return {key: entry[key] for key in ('note', 'sources', 'checked_at')}


def purge_starbucks(conn):
    """Hard-delete unselected branches and their public child rows in one transaction."""
    ids = [r['id'] for r in conn.execute('SELECT * FROM places')
           if excluded_starbucks(r['name'], json.loads(r['tags']), r['source_url'])]
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    children = {'region_places', 'catalog_photos', 'catalog_visuals', 'cafe_popularity', 'catalog_visitors'}
    for table in sorted(tables & children):
        conn.executemany(f'DELETE FROM {table} WHERE place_id=?', [(pid,) for pid in ids])
    conn.executemany('DELETE FROM places WHERE id=?', [(pid,) for pid in ids])
    conn.execute('UPDATE imports SET count=(SELECT count(*) FROM region_places rp WHERE rp.region=imports.region)')
    return len(ids)


def apply(path=None):
    """Apply the checked-in, reviewed OSM snapshot atomically after a local backup."""
    from . import place_catalog as catalog
    from datetime import datetime, timezone
    import sqlite3

    raw = json.loads((MANIFEST.parent / 'dining_osm.json').read_text(encoding='utf-8'))
    now = datetime.now(timezone.utc).isoformat()
    records = []
    for element in raw['elements']:
        place = catalog.normalize(element, now)
        if not place or not (entry := match(place)) or entry.get('starbucks_keep'):
            raise ValueError('Dining snapshot contains an unreviewed branch')
        records.append((place, entry))
    expected = {url for url, entry in entries().items() if not entry.get('starbucks_keep')}
    if {p['source_url'] for p, _ in records} != expected or len(records) != len(expected):
        raise ValueError('Incomplete or duplicate dining snapshot')
    with catalog.connect(path) as conn:
        backup = Path(path or catalog.db_path()).parent / 'backups' / ('before-dining-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.sqlite3')
        backup.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(backup) as target:
            conn.backup(target)
        added = sum(not conn.execute('SELECT 1 FROM places WHERE id=?', (p['id'],)).fetchone() for p, _ in records)
        deleted = purge_starbucks(conn)
        for p, entry in records:
            conn.execute('''INSERT INTO places (id,osm_type,osm_id,name,category,lat,lng,address,opening_hours,source_url,tags,fetched_at)
                VALUES (:id,:osm_type,:osm_id,:name,:category,:lat,:lng,:address,:opening_hours,:source_url,:tags,:fetched_at)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,category=excluded.category,lat=excluded.lat,lng=excluded.lng,
                address=excluded.address,opening_hours=excluded.opening_hours,tags=excluded.tags,fetched_at=excluded.fetched_at,active=1''', p)
            conn.execute('INSERT OR IGNORE INTO region_places VALUES (?,?)', (entry['region'] + ':dining', p['id']))
        for region in {entry['region'] for _, entry in records}:
            batch = region + ':dining'
            lat, lng, radius = catalog.REGIONS[region]
            count = conn.execute('SELECT count(*) FROM region_places WHERE region=?', (batch,)).fetchone()[0]
            conn.execute('INSERT OR REPLACE INTO imports VALUES (?,?,?,?,?,?,?)',
                         (batch, lat, lng, radius, now, raw['osm3s']['timestamp_osm_base'], count))
    return {'deleted_starbucks': deleted, 'added': added, 'reviewed_dining': len(records), 'backup': str(backup)}


if __name__ == '__main__':
    print(json.dumps(apply(), ensure_ascii=False))
