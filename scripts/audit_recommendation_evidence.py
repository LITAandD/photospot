"""Audit active places without collecting browser profiles or emitting analytics.

Use a COPY of the catalog via PLACE_CATALOG_DB. Optional --live is a read-only
aggregate export with votes/evidence; never pass session/user-level analytics.
All profile/rank comparisons below are declared synthetic scenarios.
"""
import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path

from api import photo_likes
from api.catalog_media import photos_for
from api.catalog_recommendations import recommend
from api.catalog_scoring import explanation
from api.public_place_info import ORIGINS
from api.catalog_models import PreviewQuery
from pipeline import place_catalog as catalog
from pipeline.catalog_mbti import descriptions_for
from pipeline.catalog_visitors import rankings
from pipeline.catalog_visuals import evidence_for

SCENARIOS = {
    'warm_wave_ENFJ': {'pc_season': 'spring_warm', 'body_type': 'wave', 'mbti': 'ENFJ'},
    'cool_natural_ISTP': {'pc_season': 'winter_cool', 'body_type': 'natural', 'mbti': 'ISTP'},
    'warm_straight_ISFJ': {'pc_season': 'autumn_warm', 'body_type': 'straight', 'mbti': 'ISFJ'},
}


def audit(live=None, visit_date=date(2026, 11, 13)):
    with catalog.connect() as conn:
        places = [dict(r) for r in conn.execute('SELECT * FROM places WHERE active=1 ORDER BY id')]
    ids = [p['id'] for p in places]
    media = photos_for(ids)
    votes = {(r['place_id'], r['photo_id']): {'like_count': r['like_count'], 'liked': False} for r in (live or {}).get('votes', [])}
    media = photo_likes.rank(media, votes, bool(live))
    diagnostics = {}
    evidence = evidence_for(ids, selected_photos=media, diagnostics=diagnostics)
    covers = {pid: ps[0] for pid, ps in media.items() if ps}
    if live:
        evidence.update(photo_likes._reviewed(covers, live.get('evidence', [])))
    diagnostics.update({pid: 'ready' for pid in evidence})
    descriptions = descriptions_for(ids)
    context, visitors = rankings()
    counts = {m: Counter() for m in ('color_temp', 'brightness', 'saturation', 'form', 'crowd_level', 'place_character', 'space_nature')}
    records = []
    profile = SCENARIOS['warm_wave_ENFJ']
    for place in places:
        pid = place['id']
        args = (evidence.get(pid), place, visitors.get(pid, context), descriptions.get(pid))
        scoring = explanation(profile, *args, photo_status=diagnostics[pid])
        empty = explanation({}, *args, photo_status=diagnostics[pid])
        assert empty['score'] is None and all(m['status'] == 'missing_input' for m in empty['metrics'])
        for metric in scoring['metrics']:
            counts[metric['key'].split('.')[1]][metric['evidence_status']] += 1
        records.append({'id': pid, 'name': place['name'], 'cover': covers.get(pid),
                        'photo_status': diagnostics[pid], 'evidence_ready_count': scoring['evidence_ready_count'],
                        'metrics': {m['key']: m['evidence_status'] for m in scoring['metrics']},
                        'synthetic_score': scoring['score']})
    # Public default browse is a reproducible priority proxy, NOT measured exposure.
    priority, comparisons = {}, {}
    for city, origin in ORIGINS.items():
        query = PreviewQuery(lat=origin['lat'], lng=origin['lng'], radius_m=5000, limit=12, visit_date=visit_date)
        public = recommend(query, {}, public_browse=True, detail_ids=set())['recommendations'].items
        for rank, item in enumerate(public, 1):
            priority.setdefault(item.place_id, []).append({'city': city, 'rank': rank})
        for name, profile in SCENARIOS.items():
            personalized = PreviewQuery(**{**query.model_dump(), 'profile': profile})
            items = recommend(personalized, {}, detail_ids=set())['recommendations'].items
            comparisons[f'{city}/{name}'] = [{'id': i.place_id, 'name': i.place_name, 'score': i.fit_score,
                'evaluated': sum(m.status == 'scored' for m in i.scoring.metrics)} for i in items]
    return {'catalog_count': len(places), 'photo_places': len(covers), 'exact_photo_evidence': len(evidence),
            'metrics': {k: dict(v) for k, v in counts.items()},
            'empty_profile': {'missing_input_per_metric': len(places), 'personalized_score': None, 'expected': True},
            'profile_source': 'synthetic; no browser profiles collected',
            'live_snapshot_checked_at': (live or {}).get('checked_at'),
            'cover_votes': (live or {}).get('votes', []),
            'priority_basis': 'default public browse, 4 city origins, 5 km, 12 results; NOT actual exposure',
            'priority': priority, 'comparisons': comparisons, 'places': records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--live', type=Path)
    args = parser.parse_args()
    result = audit(json.loads(args.live.read_text(encoding='utf-8')) if args.live else None)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('catalog_count', 'photo_places', 'exact_photo_evidence', 'metrics')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
