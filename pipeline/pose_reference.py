"""Reviewed head/foot coordinates for a visible person, bound to the exact photo.

These are image proportions, not inferred real-world heights or detections made
during an API request. Never infer a full body from a cropped person or reflection.
"""
import json
from pathlib import Path


REVIEWS = {(r['photo_url'], r['source_url']): r for r in json.loads(
    (Path(__file__).parent / 'data/pose_reference_reviews.json').read_text(encoding='utf-8'))}


def reference_for(photo_url, source_url):
    review = REVIEWS.get((photo_url, source_url))
    if not review:
        return None
    head, foot = review['head_y'], review['foot_y']
    if not 0 <= head < foot <= 1 or foot - head < 0.015:
        return None
    return {'height_ratio': round(foot - head, 6), 'foot_y': foot}
