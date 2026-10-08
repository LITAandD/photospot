"""Reviewed space descriptions and map classifications for explicit MBTI preferences.

No scraping during recommendations. S/N requires a source excerpt about this
exact space, not food, staff, hashtags, brand-wide copy or a photo model's guess.
"""
import argparse
from datetime import date
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from . import place_catalog as catalog
from .catalog_visitors import today

KEYWORDS = {'detail': ('디테일', '섬세', '정교', '세밀', 'detail'),
            'concept': ('컨셉', '콘셉트', '컨셉트', '테마', '세계관', 'concept', 'theme')}


def phrase_signals(excerpt):
    hits = {key: set() for key in KEYWORDS}
    for sentence in re.split(r'[.!?\n]', excerpt.lower()):
        # Reviewed snippets are positive descriptions. Conservatively skip
        # clauses that deny a feature rather than treating the word as evidence.
        if re.search(r'없|아니|않|부족|별로|\b(?:no|not|without)\b', sentence):
            continue
        for key, words in KEYWORDS.items():
            for word in words:
                pattern = rf'\b{word}s?\b' if word.isascii() else re.escape(word)
                if re.search(pattern, sentence): hits[key].add(word)
    return {key: sorted(words) for key, words in hits.items()}


def initialize(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS catalog_descriptions (
        place_id TEXT NOT NULL, place_source TEXT NOT NULL, source_url TEXT NOT NULL,
        provider TEXT NOT NULL, label TEXT NOT NULL, excerpt TEXT NOT NULL,
        checked_at TEXT NOT NULL, scope TEXT NOT NULL,
        PRIMARY KEY(place_id,source_url))''')


def import_records(records, path=None, as_of=None):
    as_of = as_of or today()
    checked = []
    with catalog.connect(path) as conn:
        initialize(conn)
        places = {r['id']: dict(r) for r in conn.execute('SELECT * FROM places')}
        for row in records:
            place = places.get(row['place_id'])
            url = urlsplit(row['source_url'])
            provider = row['provider']
            allowed = ((provider == 'naver' and url.hostname in {'map.naver.com', 'pcmap.place.naver.com', 'm.place.naver.com'}
                        and re.search(r'/(?:place|restaurant|cafe)/\d+', url.path))
                       or (provider == 'instagram' and url.hostname in {'instagram.com', 'www.instagram.com'}
                           and re.search(r'/(?:p|reel)/[\w-]+/', url.path)))
            if (not place or row['place_source'] != place['source_url'] or row['place_name'] != place['name']
                    or abs(row['lat'] - place['lat']) > .0001 or abs(row['lng'] - place['lng']) > .0001
                    or url.scheme != 'https' or url.username or url.password or not allowed
                    or date.fromisoformat(row['checked_at']) > as_of or row.get('scope') != 'space'
                    or not row['label'].strip() or not 1 <= len(row['excerpt'].strip()) <= 300):
                raise ValueError('Description must be a reviewed exact-branch space excerpt')
            checked.append(tuple(row[k] for k in ('place_id', 'place_source', 'source_url', 'provider', 'label', 'excerpt', 'checked_at', 'scope')))
        conn.executemany('''INSERT INTO catalog_descriptions VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(place_id,source_url) DO UPDATE SET label=excluded.label, excerpt=excluded.excerpt,
            checked_at=excluded.checked_at, scope=excluded.scope WHERE excluded.checked_at>=catalog_descriptions.checked_at''', checked)
    return len(checked)


def descriptions_for(place_ids, path=None, as_of=None):
    ids = set(place_ids)
    if not ids: return {}
    result = {}
    with catalog.connect(path) as conn:
        initialize(conn)
        rows = conn.execute('''SELECT d.* FROM catalog_descriptions d JOIN places p ON p.id=d.place_id
            WHERE p.active=1 AND p.source_url=d.place_source AND d.checked_at<=?''', ((as_of or today()).isoformat(),))
        for row in rows:
            if row['place_id'] in ids: result.setdefault(row['place_id'], []).append(dict(row))
    return result


def description_character(entries):
    found, sources = set(), []
    for entry in entries or []:
        signals = phrase_signals(entry['excerpt'])
        found.update(key for key, hits in signals.items() if hits)
        sources.append({'url': entry['source_url'], 'label': entry['label'], 'excerpt': entry['excerpt'],
                        'checked_at': entry['checked_at'], 'keywords': sorted({w for hits in signals.values() for w in hits})})
    value = 'mixed' if len(found) == 2 else next(iter(found), None)
    return value, sources


def space_nature(place):
    if not place: return None, '', []
    tags = place.get('tags') or {}
    if isinstance(tags, str): tags = json.loads(tags)
    kind = place.get('category')
    built = (tags.get('building') not in {None, 'no'} or tags.get('historic') in
             {'castle', 'city_gate', 'building', 'palace', 'monument', 'tower', 'fort', 'manor'}
             or kind in {'cafe', 'bakery', 'restaurant', 'museum', 'gallery', 'cultural_venue'})
    natural = (kind in {'park', 'waterfront', 'scenic'} or tags.get('natural') in
               {'beach', 'wood', 'water', 'peak', 'cliff', 'wetland', 'grassland', 'heath', 'bay'}
               or tags.get('leisure') in {'garden', 'nature_reserve'})
    value = 'mixed' if built and natural else 'architecture' if built else 'nature' if natural else None
    note = {'architecture': '건축물 중심', 'nature': '자연물 중심', 'mixed': '건축물·자연물 혼합'}.get(value, '')
    from .place_categories import CATEGORIES
    details = [f"장소 유형: {CATEGORIES.get(kind, kind)}"]
    details.extend(f'{k}={tags[k]}' for k in ('building', 'historic', 'natural', 'leisure') if k in tags)
    sources = [{'url': place['source_url'], 'label': 'OpenStreetMap 공간 분류', 'excerpt': ' · '.join(details)}] if value and place.get('source_url') else []
    return value, '지도 유형·태그 기준: ' + note, sources


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    args = parser.parse_args()
    print('Imported space descriptions:', import_records(json.loads(args.file.read_text(encoding='utf-8'))))
