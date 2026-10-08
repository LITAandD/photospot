"""Reviewed, branch-specific public Instagram permalinks for official embeds.

No image files, CDN URLs, captions, counts or oEmbed metadata are stored or scored.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from . import place_catalog as catalog
from .cafe_photos import display_name

MANIFEST = Path(__file__).with_name('data') / 'instagram_places.json'


def canonical_post(value):
    try:
        url = urlsplit(value)
        if url.scheme != 'https' or url.hostname not in {'instagram.com', 'www.instagram.com'} or url.username or url.password or url.port:
            raise ValueError('Invalid Instagram host')
        match = re.fullmatch(r'/(?:[A-Za-z0-9._]{1,30}/)?(p|reel)/([A-Za-z0-9_-]{5,64})/?', url.path)
        if not match: raise ValueError('An individual public post is required')
        return f'https://www.instagram.com/{match[1]}/{match[2]}/'
    except (TypeError, AttributeError) as exc:
        raise ValueError('Invalid Instagram URL') from exc


def initialize(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS catalog_instagram (
        place_id TEXT NOT NULL, permalink TEXT NOT NULL, label TEXT NOT NULL,
        evidence_url TEXT NOT NULL, checked_at TEXT NOT NULL,
        PRIMARY KEY(place_id, permalink))''')


def apply(path=None, manifest=MANIFEST):
    entries = json.loads(Path(manifest).read_text(encoding='utf-8'))['posts']
    with catalog.connect(path) as conn:
        prepared = []
        for entry in entries:
            row = conn.execute('SELECT * FROM places WHERE source_url=? AND active=1', (entry['place_source'],)).fetchone()
            if row is None or row['category'] not in {'cafe', 'bakery', 'restaurant'} or display_name(dict(row)) != entry['place_name']:
                raise ValueError('Unmatched dining branch: ' + entry['place_name'])
            checked = date.fromisoformat(entry['checked_at'])
            if checked > date.today(): raise ValueError('Future review date')
            evidence = urlsplit(entry['evidence_url'])
            if evidence.scheme != 'https' or not evidence.hostname or evidence.username or evidence.password:
                raise ValueError('Invalid evidence URL')
            label = entry['label'].strip()
            if not label or len(label) > 120: raise ValueError('Invalid label')
            prepared.append((row['id'], canonical_post(entry['permalink']), label, entry['evidence_url'], checked.isoformat()))
        initialize(conn)
        # Replace the reviewed set atomically, including withdrawn references.
        conn.execute('DELETE FROM catalog_instagram')
        conn.executemany('INSERT INTO catalog_instagram VALUES (?,?,?,?,?)', prepared)
    return {'places': len({r[0] for r in prepared}), 'posts': len(prepared)}


def posts_for(place_ids, path=None):
    ids = list(set(place_ids))
    result = defaultdict(list)
    if not ids: return result
    with catalog.connect(path) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='catalog_instagram'").fetchone():
            return result
        for start in range(0, len(ids), 400):
            batch = ids[start:start + 400]
            rows = conn.execute('SELECT i.* FROM catalog_instagram i JOIN places p ON p.id=i.place_id '
                                'WHERE p.active=1 AND i.place_id IN (' + ','.join('?' for _ in batch) + ') ORDER BY i.rowid', batch)
            for row in rows:
                try: permalink = canonical_post(row['permalink'])
                except ValueError: continue
                result[row['place_id']].append({'permalink': permalink, 'label': row['label'], 'checked_at': row['checked_at']})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, default=MANIFEST)
    args = parser.parse_args()
    print(json.dumps(apply(manifest=args.manifest), ensure_ascii=False))
