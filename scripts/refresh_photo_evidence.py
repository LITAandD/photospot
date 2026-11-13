"""Analyze only eligible CURRENT covers from an audit; export geometry for review.

No form is auto-approved, no likes or cloud data are written. Work on a catalog
copy and inspect the report before exporting. Source and licence identity must
still match the served gallery. Stale audit entries fail closed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
from PIL import Image

from api.catalog_media import photos_for, reusable
from api.photo_likes import photo_id, rank
from pipeline.catalog_geometry import geometry_candidates
from pipeline.catalog_visuals import color_attributes, read_photo, store

METHOD = 'photo-color-v2'


def refresh(audit, output, limit=100):
    priority = audit['priority']
    rows = sorted((r for r in audit['places'] if r.get('cover') and r['photo_status'] in {'analysis_pending', 'cover_mismatch'}),
                  key=lambda r: (r['id'] not in priority, min((p['rank'] for p in priority.get(r['id'], [])), default=99), r['name']))[:limit]
    current = photos_for(r['id'] for r in rows)
    votes = {(r['place_id'], r['photo_id']): {'like_count': r['like_count'], 'liked': False}
             for r in audit.get('cover_votes', [])}
    current = rank(current, votes, bool(audit.get('live_snapshot_checked_at')))
    def process(row):
        pid, cover = row['id'], row['cover']
        result = {'place_id': pid, 'name': row['name'], 'photo_id': photo_id(cover), 'photo': cover,
                  'priority': priority.get(pid, []), 'checked_at': datetime.now(timezone.utc).isoformat()}
        candidates = current.get(pid, [])
        if not reusable(cover) or not candidates or photo_id(candidates[0]) != photo_id(cover):
            return {**result, 'status': 'ineligible_or_stale'}
        try:
            data = read_photo(cover['url'])
            with Image.open(BytesIO(data)) as image:
                colors = color_attributes(image)
                geometry = geometry_candidates(image)
            return {**result, 'status': 'analyzed', 'attributes': colors,
                    'image_sha256': hashlib.sha256(data).hexdigest(), 'geometry': geometry}
        except Exception as error:
            return {**result, 'status': 'unavailable', 'error_type': type(error).__name__}
    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(process, rows):
            if result['status'] == 'analyzed':
                store(result['place_id'], result['photo'], result['attributes'],
                      f"사진 전체 색 통계 ({METHOD}; photo_id={result['photo_id']}; sha256={result['image_sha256']})")
            results.append(result)
            output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
            print(result['name'], result['status'], flush=True)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    refresh(json.loads(args.audit.read_text(encoding='utf-8')), args.output, args.limit)
