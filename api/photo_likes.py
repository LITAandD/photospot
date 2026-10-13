"""Shared likes in PostgreSQL; never store votes in Vercel's temporary catalog.

One row per browser/account and photo. Writes express desired state, so retries
and double clicks cannot increment twice. Totals and viewer state come from the
same query. Neither birth/profile data nor client IPs are written here.
"""
from functools import lru_cache
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from pipeline.photo_identity import photo_id


def configured():
    return bool(os.environ.get('PHOTO_LIKES_DATABASE_URL'))


@lru_cache(maxsize=2)
def pool(dsn):
    return ConnectionPool(dsn, min_size=0, max_size=3, timeout=5,
                          kwargs={'connect_timeout': 5}, open=True)


@contextmanager
def connection():
    dsn = os.environ.get('PHOTO_LIKES_DATABASE_URL')
    if not dsn:
        raise RuntimeError('Photo likes database is not configured')
    with pool(dsn).connection() as conn:
        # Neon transaction pooling rejects statement_timeout startup options.
        # A transaction-local setting is supported and cannot leak to a new user.
        conn.execute("SET LOCAL statement_timeout = '5s'")
        yield conn


def voter_hash(identity):
    return hashlib.sha256(identity.encode()).hexdigest()


def snapshot(ids, identity=None):
    """One aggregate query for the entire recommendation candidate set."""
    ids = list(ids)
    if not ids or not configured():
        return {}, False
    with connection() as conn:
        rows = conn.execute('''SELECT place_id, photo_id, count(*) AS total,
            bool_or(voter_hash=%s) AS liked FROM photo_likes
            WHERE place_id=ANY(%s) GROUP BY place_id, photo_id''',
            (voter_hash(identity) if identity else '', ids)).fetchall()
    return {(pid, photo): {'like_count': total, 'liked': liked} for pid, photo, total, liked in rows}, True


def rank(photos, votes, enabled):
    # Stable sort preserves close-space/source priority when vote totals tie.
    return {pid: sorted([{**p, 'photo_id': photo_id(p), 'like_count': 0, 'liked': False,
                          'likes_enabled': enabled, **votes.get((pid, photo_id(p)), {})} for p in ps],
                        key=lambda p: -p['like_count']) for pid, ps in photos.items()}


def set_like(place_id, photo, identity, liked):
    key = (place_id, photo_id(photo), voter_hash(identity))
    with connection() as conn:
        # Serialize simultaneous changes to the same photo, including unlike vs. like.
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', (place_id + ':' + key[1],))
        if liked:
            conn.execute('INSERT INTO photo_likes (place_id,photo_id,voter_hash) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING', key)
        else:
            conn.execute('DELETE FROM photo_likes WHERE place_id=%s AND photo_id=%s AND voter_hash=%s', key)
        total = conn.execute('SELECT count(*) FROM photo_likes WHERE place_id=%s AND photo_id=%s', key[:2]).fetchone()[0]
    # The pool transaction commits before this response can be sent.
    return {'photo_id': key[1], 'like_count': total, 'liked': liked}


def evidence_for(covers):
    import json
    from pipeline.catalog_visuals import reviewed_evidence
    if not covers or not configured():
        return {}
    with connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT * FROM liked_photo_evidence WHERE place_id=ANY(%s)', (list(covers),))
        result = {}
        for row in cur:
            cover = covers[row['place_id']]
            if (row['photo_id'] == photo_id(cover) and
                    (row['photo_url'], row['source_url']) == (cover['url'], cover['source_url'])):
                reviewed = reviewed_evidence({**row, 'attributes': json.dumps(row['attributes'])})
                if reviewed:
                    result[row['place_id']] = reviewed
        return result


def analyze_photo(place_id, photo):
    """Called only on a like, outside any DB connection; failures stay unassessed."""
    from io import BytesIO
    from PIL import Image
    from pipeline.catalog_visuals import color_attributes, read_photo, reviewed_evidence
    with Image.open(BytesIO(read_photo(photo['url']))) as image:
        attributes = color_attributes(image)
    row = {'place_id': place_id, 'photo_url': photo['url'], 'source_url': photo['source_url'],
           'attributes': attributes, 'method': '대표사진 색조 통계 · 좋아요 선택'}
    # Exact-image human geometry reviews can supplement measured color; other
    # images' body-type tags must never leak onto the newly selected cover.
    import json
    reviewed = reviewed_evidence({**row, 'attributes': json.dumps(attributes)})
    return reviewed


def ensure_evidence(place_id, photo):
    from pipeline.catalog_visuals import evidence_for as local_evidence
    if local_evidence([place_id], selected_photos={place_id: [photo]}).get(place_id):
        return
    if evidence_for({place_id: photo}).get(place_id):
        return
    observed = analyze_photo(place_id, photo)
    if not observed:
        return
    with connection() as conn:
        conn.execute('''INSERT INTO liked_photo_evidence
            (place_id,photo_id,photo_url,source_url,attributes,method) VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (place_id,photo_id) DO UPDATE SET photo_url=EXCLUDED.photo_url,
            source_url=EXCLUDED.source_url,attributes=EXCLUDED.attributes,method=EXCLUDED.method,checked_at=now()''',
            (place_id, photo_id(photo), photo['url'], photo['source_url'], Jsonb(observed['attributes']), observed['method']))


def migrate():
    """Run explicitly at provisioning/deploy time, never inside a user request."""
    with psycopg.connect(os.environ['PHOTO_LIKES_DATABASE_URL'], connect_timeout=10) as conn:
        conn.execute(Path(__file__).with_suffix('.sql').read_text(encoding='utf-8'))


if __name__ == '__main__':
    migrate()
    print('Photo likes tables ready')
