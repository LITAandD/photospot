"""Shared likes in PostgreSQL; never store votes in Vercel's temporary catalog.

One row per browser/account and photo. Writes express desired state, so retries
and double clicks cannot increment twice. Totals and viewer state come from the
same query. Neither birth/profile data nor client IPs are written here.

Reads fail soft: when the store is slow or down, recommendations, place detail
and bookmarks continue with likes_enabled=false and the store is skipped for a
short cooldown. Only like writes report the outage to the browser.
"""
from contextlib import contextmanager
import hashlib
import logging
import os
from pathlib import Path
import threading
import time

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool, PoolTimeout

from pipeline.photo_identity import photo_id

log = logging.getLogger(__name__)
POOL_NAME = 'photo-likes'


class _QuietRetries(logging.Filter):
    # This pool retries in the background and would warn on every attempt; the
    # outage is logged once a minute below. Other pools (the account DB) keep theirs.
    def filter(self, record):
        return record.levelno >= logging.ERROR or POOL_NAME not in record.getMessage()


logging.getLogger('psycopg.pool').addFilter(_QuietRetries())

READ_TIMEOUT_S = 2.0        # wait for a pooled connection on the read path
WRITE_TIMEOUT_S = 5.0
CONNECT_TIMEOUT_S = 2       # libpq rounds anything lower up to 2 seconds
OUTAGE_COOLDOWN_S = 20.0    # reads skip the store this long after a failure
STORE_ERRORS = (psycopg.Error, PoolTimeout, OSError)
_state = {'outage_until': 0.0, 'logged_at': 0.0}
_local = threading.local()  # evidence rows handed from snapshot() to evidence_for()


class RevokedVoter(Exception):
    pass


def configured():
    return bool(os.environ.get('PHOTO_LIKES_DATABASE_URL'))


def available():
    """Configured and not inside the cooldown that follows a store failure."""
    return configured() and time.monotonic() >= _state['outage_until']


def unavailable(exc):
    """Record a store failure: reads degrade until the cooldown ends, logged once a minute."""
    now = time.monotonic()
    _state['outage_until'] = now + OUTAGE_COOLDOWN_S
    if now - _state['logged_at'] >= 60:
        _state['logged_at'] = now
        log.warning('Photo likes store unavailable: %s', type(exc).__name__)


def min_votes():
    return max(1, int(os.environ.get('PHOTO_LIKES_MIN_VOTES', '5')))


def min_margin():
    return max(1, int(os.environ.get('PHOTO_LIKES_MIN_MARGIN', '2')))


_pools = {}
_pools_lock = threading.Lock()


def pool(dsn):
    """One pool per DSN and process, created under a lock: concurrent first calls
    must not leave orphan pools whose worker threads outlive the request."""
    with _pools_lock:
        found = _pools.get(dsn)
        if found is None:
            # autocommit: a read is one simple query (SET LOCAL + SELECTs) without
            # BEGIN/COMMIT round trips; writes open explicit transactions in connection().
            # min_size=1 keeps a warm connection on instances that stay alive.
            found = _pools[dsn] = ConnectionPool(dsn, name=POOL_NAME, min_size=1, max_size=3, timeout=READ_TIMEOUT_S,
                                                 kwargs={'connect_timeout': CONNECT_TIMEOUT_S, 'autocommit': True}, open=True)
        return found


pool.cache_clear = _pools.clear  # type: ignore[attr-defined]


def _dsn():
    dsn = os.environ.get('PHOTO_LIKES_DATABASE_URL')
    if not dsn:
        raise RuntimeError('Photo likes database is not configured')
    return dsn


@contextmanager
def connection(timeout=WRITE_TIMEOUT_S):
    """A transaction for writes; the pool commits it before the response is sent."""
    if not available():
        # Known outage: answer at once instead of holding the request for the pool timeout.
        raise PoolTimeout('photo likes store is in outage cooldown')
    with pool(_dsn()).connection(timeout=timeout) as conn, conn.transaction():
        # Neon transaction pooling rejects statement_timeout startup options.
        # A transaction-local setting is supported and cannot leak to a new user.
        conn.execute("SET LOCAL statement_timeout = '5s'")
        yield conn


def voter_hash(identity):
    return hashlib.sha256(identity.encode()).hexdigest()


# One network round trip for the whole candidate set: totals, the viewer's own
# votes and the stored exact-image observations. The implicit transaction of a
# multi-statement query scopes SET LOCAL to these statements only.
READ_SQL = sql.SQL('''SET LOCAL statement_timeout = '2s';
SELECT place_id, photo_id, count(*)::int AS total, bool_or(voter_hash = {voter}) AS liked
  FROM photo_likes WHERE place_id = ANY({ids}) GROUP BY place_id, photo_id;
SELECT place_id, photo_id, photo_url, source_url, attributes, method
  FROM liked_photo_evidence WHERE place_id = ANY({ids})''')


def _read(ids, identity):
    with pool(_dsn()).connection(timeout=READ_TIMEOUT_S) as conn:
        cur = conn.execute(READ_SQL.format(voter=sql.Literal(voter_hash(identity) if identity else ''),
                                           ids=sql.Literal(list(ids))))
        cur.nextset()
        votes = {(pid, photo): {'like_count': total, 'liked': liked} for pid, photo, total, liked in cur.fetchall()}
        cur.nextset()
        columns = [c.name for c in cur.description]
        evidence = [dict(zip(columns, row)) for row in cur.fetchall()]
    return votes, evidence


def read(ids, identity=None):
    """(votes, evidence rows, enabled) for a candidate set; degrades to ({}, [], False)."""
    ids = list(ids)
    if not ids or not available():
        return {}, [], False
    try:
        votes, evidence = _read(ids, identity)
    except STORE_ERRORS as exc:
        unavailable(exc)
        return {}, [], False
    return votes, evidence, True


def snapshot(ids, identity=None):
    """Vote totals for the recommendation candidate set; never raises for store outages."""
    ids = list(ids)
    votes, evidence, enabled = read(ids, identity)
    # recommend() asks for cover evidence right after this, in the same thread.
    _local.evidence = (time.monotonic(), set(ids), evidence) if enabled else None
    return votes, enabled


def rank(photos, votes, enabled):
    """Every photo shows its total, but a liked photo leads (and becomes the
    scored cover) only with at least PHOTO_LIKES_MIN_VOTES votes and a margin
    over the curated cover. Otherwise a cleared cookie would re-pick the cover
    for every visitor."""
    floor, margin = min_votes(), min_margin()
    result = {}
    for pid, ps in photos.items():
        ranked = [{**p, 'photo_id': photo_id(p), 'like_count': 0, 'liked': False, 'likes_enabled': enabled,
                   **votes.get((pid, photo_id(p)), {})} for p in ps]
        curated = ranked[0]['like_count'] if ranked else 0
        # Stable sort keeps close-space/source priority among ties and non-leaders.
        result[pid] = sorted(ranked, key=lambda p: -p['like_count']
                             if p['like_count'] >= floor and p['like_count'] >= curated + margin else 1)
    return result


def set_like(place_id, photo, identity, liked):
    key = (place_id, photo_id(photo), voter_hash(identity))
    with connection() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', ('voter:' + key[2],))
        if conn.execute('SELECT 1 FROM revoked_photo_voters WHERE voter_hash=%s', (key[2],)).fetchone():
            raise RevokedVoter()
        # Serialize simultaneous changes to the same photo, including unlike vs. like.
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', (place_id + ':' + key[1],))
        if liked:
            conn.execute('INSERT INTO photo_likes (place_id,photo_id,voter_hash) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING', key)
        else:
            conn.execute('DELETE FROM photo_likes WHERE place_id=%s AND photo_id=%s AND voter_hash=%s', key)
        total = conn.execute('SELECT count(*) FROM photo_likes WHERE place_id=%s AND photo_id=%s', key[:2]).fetchone()[0]
    # The pool transaction commits before this response can be sent.
    return {'photo_id': key[1], 'like_count': total, 'liked': liked}


def revoke(hashed):
    with connection() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', ('voter:' + hashed,))
        conn.execute('INSERT INTO revoked_photo_voters (voter_hash) VALUES (%s) ON CONFLICT DO NOTHING', (hashed,))
        conn.execute('DELETE FROM photo_likes WHERE voter_hash=%s', (hashed,))


def remove_voter(identity):
    """Account deletion; returns False when the store is down so the account
    deletion itself still completes. The logged hash identifies no person once
    the account row is gone; `python -m api.photo_likes revoke <hash>` finishes it."""
    if not configured():
        return True
    hashed = voter_hash(identity)
    try:
        revoke(hashed)
    except STORE_ERRORS as exc:
        unavailable(exc)
        log.error('Photo likes store unavailable during account deletion; revoke voter_hash=%s later (%s)',
                  hashed, type(exc).__name__)
        return False
    return True


def _reviewed(covers, rows):
    import json
    from pipeline.catalog_visuals import reviewed_evidence
    result = {}
    for row in rows:
        cover = covers.get(row['place_id'])
        if cover and row['photo_id'] == photo_id(cover) and (row['photo_url'], row['source_url']) == (cover['url'], cover['source_url']):
            reviewed = reviewed_evidence({**row, 'attributes': json.dumps(row['attributes'])})
            if reviewed:
                result[row['place_id']] = reviewed
    return result


def evidence_for(covers):
    """Exact-image observations for the selected covers; never raises for store outages.

    Reuses the rows snapshot() just read for a superset of these places (same
    thread, a few seconds) so a recommendation costs one store round trip.
    """
    if not covers or not available():
        return {}
    handoff, _local.evidence = getattr(_local, 'evidence', None), None
    if handoff and time.monotonic() - handoff[0] < 5 and set(covers) <= handoff[1]:
        rows = handoff[2]
    else:
        _, rows, enabled = read(covers)
        if not enabled:
            return {}
    return _reviewed(covers, rows)


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


def analyze_later(place_id, photo):
    """Background task after a like response: a photo host outage cannot undo a
    committed vote or attach another picture's observations. The next like of
    the same photo retries the missing analysis."""
    try:
        ensure_evidence(place_id, photo)
    except Exception as exc:
        log.warning('Photo analysis unavailable: %s', type(exc).__name__)


def prune(likes_months=12, events_days=90):
    """개인정보처리방침의 보관 기간(좋아요 12개월·익명 이벤트 90일)이 지난 행을 지운다. (지운 좋아요 수, 지운 이벤트 수)"""
    with connection() as conn:
        likes_gone = conn.execute('DELETE FROM photo_likes WHERE created_at < now() - make_interval(months => %s)', (likes_months,)).rowcount
        events_gone = conn.execute('DELETE FROM analytics_events WHERE created_at < now() - make_interval(days => %s)', (events_days,)).rowcount
    return likes_gone, events_gone


def probe(timeout=1.0):
    """Health detail: None when not configured, else whether the store answers in time."""
    if not configured():
        return None
    try:
        with pool(_dsn()).connection(timeout=timeout) as conn:
            conn.execute("SET LOCAL statement_timeout = '1s'; SELECT 1")
    except STORE_ERRORS:
        return False
    return True


def migrate():
    """Run explicitly at provisioning/deploy time, never inside a user request."""
    with psycopg.connect(os.environ['PHOTO_LIKES_DATABASE_URL'], connect_timeout=10) as conn:
        conn.execute(Path(__file__).with_suffix('.sql').read_text(encoding='utf-8'))


if __name__ == '__main__':
    import sys
    if sys.argv[1:2] == ['revoke']:
        for hashed in sys.argv[2:]:
            revoke(hashed)
        print('Revoked', len(sys.argv) - 2, 'voter hash(es)')
    elif sys.argv[1:2] == ['prune']:
        likes_gone, events_gone = prune()
        print(f'Pruned {likes_gone} like(s) older than 12 months and {events_gone} event(s) older than 90 days')
    else:
        migrate()
        print('Photo likes tables ready')
