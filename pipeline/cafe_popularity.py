"""Verified branch-level review/feed observations; no network calls during recommendation.

Import reviewed public counts with --import-json. With server-only NAVER_CLIENT_ID
and NAVER_CLIENT_SECRET, --naver-query imports the official sort=comment top 5.
That API supplies a review ordering, NOT visitor-review counts or Instagram activity.
"""
import argparse
from datetime import date
import html
import json
import math
import os
from pathlib import Path
import re
from typing import Literal
from urllib.parse import urlencode, urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import place_catalog as catalog

LABELS = {
    'naver_reviews': '네이버 리뷰',
    'instagram_place_posts': '인스타그램 장소 게시물',
    'naver_local_rank': '네이버 지역 검색 리뷰순',
}


class Observation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    place_id: str
    place_name: str
    lat: float = Field(ge=33, le=39)
    lng: float = Field(ge=124, le=132)
    metric: Literal['naver_reviews', 'instagram_place_posts', 'naver_local_rank']
    value: int = Field(ge=0, le=1_000_000_000, strict=True)
    source_url: str
    checked_at: date
    scope: str = Field(min_length=1, max_length=200)

    @model_validator(mode='after')
    def valid_source(self):
        url = urlsplit(self.source_url)
        domains = {'instagram.com', 'www.instagram.com'} if self.metric.startswith('instagram') else {
            'map.naver.com', 'm.place.naver.com', 'pcmap.place.naver.com', 'openapi.naver.com'}
        if url.scheme != 'https' or url.hostname not in domains or url.username or url.password or url.port:
            raise ValueError('Use the original HTTPS Naver/Instagram source URL')
        if self.checked_at > date.today():
            raise ValueError('A future date is not an observation')
        if self.metric == 'naver_local_rank' and not 1 <= self.value <= 5:
            raise ValueError('The official local search API returns at most five ranks')
        return self


def initialize(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS cafe_popularity (
        place_id TEXT NOT NULL REFERENCES places(id), metric TEXT NOT NULL,
        value INTEGER NOT NULL, source_url TEXT NOT NULL, checked_at TEXT NOT NULL,
        scope TEXT NOT NULL, PRIMARY KEY(place_id, metric))''')


def import_observations(raw, path=None):
    """Validate the entire batch before committing; preserve newer observations."""
    entries = [Observation.model_validate(r) for r in raw]
    with catalog.connect(path) as conn:
        initialize(conn)
        for entry in entries:
            row = conn.execute('SELECT * FROM places WHERE id=?', (entry.place_id,)).fetchone()
            if (not row or not row['active'] or row['category'] != 'cafe' or row['name'] != entry.place_name
                    or catalog.distance_m(entry.lat, entry.lng, row) > 100):
                raise ValueError('Observation must match an active cafe name, ID and branch coordinates')
            conn.execute('''INSERT INTO cafe_popularity VALUES (?,?,?,?,?,?)
                ON CONFLICT(place_id,metric) DO UPDATE SET value=excluded.value,
                source_url=excluded.source_url, checked_at=excluded.checked_at, scope=excluded.scope
                WHERE excluded.checked_at >= cafe_popularity.checked_at''',
                (entry.place_id, entry.metric, entry.value, entry.source_url, entry.checked_at.isoformat(), entry.scope))
    return len(entries)


def popularity_for(ids, path=None, today=None):
    ids = list(ids)
    if not ids: return {}
    today = today or date.today()
    result = {}
    with catalog.connect(path) as conn:
        initialize(conn)
        for start in range(0, len(ids), 400):
            batch = ids[start:start + 400]
            rows = conn.execute(f'''SELECT cp.* FROM cafe_popularity cp JOIN places p ON p.id=cp.place_id
                WHERE p.category='cafe' AND cp.place_id IN ({','.join('?' for _ in batch)})
                ORDER BY cp.metric''', batch)
            for row in rows:
                age = (today - date.fromisoformat(row['checked_at'])).days
                if age < 0 or age > (30 if row['metric'] == 'naver_local_rank' else 90): continue
                result.setdefault(row['place_id'], []).append({
                    'metric': row['metric'], 'label': LABELS[row['metric']], 'value': row['value'],
                    'source_url': row['source_url'], 'checked_at': row['checked_at'], 'scope': row['scope']})
    return result


def popularity_score(signals):
    """A capped tie-breaker, separate from personal fit; do not add overlapping counts."""
    scores = [max(0, 60 - 10 * s['value']) if s['metric'] == 'naver_local_rank'
              else min(100, 20 * math.log10(1 + s['value'])) for s in signals]
    return max(scores, default=0)


def normalized_name(value):
    return re.sub(r'[^\w]', '', html.unescape(re.sub(r'<[^>]+>', '', value))).casefold()


def naver_observations(payload, query, path=None):
    """Only exact names at the same branch location; ambiguous matches are skipped."""
    if not isinstance(payload.get('items'), list): raise ValueError('Invalid Naver result')
    observations = []
    for rank, item in enumerate(payload['items'][:5], 1):
        if not any(word in item.get('category', '') for word in ['카페', '커피']): continue
        try:
            lat, lng = float(item['mapy']) / 10_000_000, float(item['mapx']) / 10_000_000
        except (KeyError, ValueError, TypeError): continue
        if not (33 <= lat <= 39 and 124 <= lng <= 132): continue
        matches = [p for p in catalog.search(lat, lng, 100, path=path)
                   if p['category'] == 'cafe' and normalized_name(p['name']) == normalized_name(item.get('title', ''))]
        if len(matches) != 1: continue
        place = matches[0]
        observations.append(dict(place_id=place['id'], place_name=place['name'], lat=lat, lng=lng,
            metric='naver_local_rank', value=rank, checked_at=date.today().isoformat(), scope=query,
            source_url='https://openapi.naver.com/v1/search/local.json?' + urlencode({'query': query, 'display': 5, 'sort': 'comment'})))
    return observations


def fetch_naver(query):
    from .naver_local import NaverLocalClient
    client_id, secret = os.getenv('NAVER_CLIENT_ID'), os.getenv('NAVER_CLIENT_SECRET')
    if not client_id or not secret:
        raise ValueError('Set server-only NAVER_CLIENT_ID and NAVER_CLIENT_SECRET in .env')
    return {'items': NaverLocalClient(client_id, secret).search(query, sort='comment')}


def main():
    from dotenv import load_dotenv
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--import-json', type=Path)
    group.add_argument('--naver-query')
    args = parser.parse_args()
    try:
        rows = naver_observations(fetch_naver(args.naver_query), args.naver_query) if args.naver_query else json.loads(args.import_json.read_text(encoding='utf-8'))
        print(json.dumps({'imported': import_observations(rows)}))
    except Exception as error:
        # Never dump provider request headers or credential-bearing errors.
        parser.exit(1, f'Popularity import failed ({type(error).__name__}); check input or server credentials.\n')


if __name__ == '__main__': main()
