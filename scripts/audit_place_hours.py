"""Audit every active catalog row, recording covered and unresolved hours.

This audits connected source data, not a claim of individual web verification
for every venue. The unresolved inventory is preserved for further enrichment.
"""
from collections import Counter
from datetime import datetime
import json
from zoneinfo import ZoneInfo

from pipeline import place_catalog as catalog, place_hours, official_cafe_photos, place_quality
from pipeline.catalog_photos import photo_counts_for
from pipeline.place_categories import group_for


def audit():
    today = datetime.now(ZoneInfo('Asia/Seoul')).date()
    with catalog.connect() as con:
        rows = [dict(r) for r in con.execute('SELECT * FROM places WHERE active=1')]
    rows = official_cafe_photos.enrich_places(rows)
    photos = photo_counts_for(r['id'] for r in rows)
    covered, unresolved, excluded = [], [], []
    for row in rows:
        reason = place_quality.row_exclusion(row)
        if reason:
            excluded.append({'place_id': row['id'], 'name': row['name'], 'reason': reason})
            continue
        hours = place_hours.hours_for(row, today, today)
        item = {'place_id': row['id'], 'name': row['name'], 'group': group_for(row['category']),
                'has_photos': bool(photos.get(row['id'])), 'source_url': row['source_url']}
        if hours:
            covered.append({**item, 'provider': hours['provider'], 'schedule_kind': hours.get('schedule_kind', 'regular'),
                            'summary': hours['summary'], 'source_url': hours['source_url'], 'checked_at': hours['checked_at']})
        else:
            unresolved.append({**item, 'reason': 'no_hours_in_connected_sources',
                               'address': row['address'], 'lat': row['lat'], 'lng': row['lng']})
    summary = {'checked_at': today.isoformat(), 'scope': 'all active catalog rows; connected public sources only',
               'catalog_rows': len(rows), 'excluded': len(excluded), 'displayable_hours': len(covered),
               'unresolved': len(unresolved), 'by_provider': dict(Counter(r['provider'] for r in covered)),
               'by_schedule_kind': dict(Counter(r['schedule_kind'] for r in covered)),
               'by_group': {group: {'covered': sum(r['group'] == group for r in covered),
                                    'unresolved': sum(r['group'] == group for r in unresolved)}
                            for group in ['cafe', 'travel', 'festival']},
               'photographed_cafes': {'covered': sum(r['group'] == 'cafe' and r['has_photos'] for r in covered),
                                     'unresolved': sum(r['group'] == 'cafe' and r['has_photos'] for r in unresolved)}}
    root = catalog.ROOT / 'artifacts'
    root.mkdir(exist_ok=True)
    for name, data in [('place-hours-coverage', summary), ('place-hours-covered', covered),
                       ('place-hours-unresolved', unresolved), ('place-hours-excluded', excluded)]:
        (root / (name + '.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


if __name__ == '__main__': print(json.dumps(audit(), ensure_ascii=True, indent=2))
