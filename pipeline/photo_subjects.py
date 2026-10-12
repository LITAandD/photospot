"""Reviewed space galleries: keep people as context, exclude people as the subject.

Busy venue categories can contain entire artist/event albums. For reviewed venues,
new or changed photos remain hidden until confirmed as a space photograph. Import
records stay intact for provenance; all public photo readers apply this policy.
"""
import json
from pathlib import Path


REVIEWS = json.loads((Path(__file__).parent / 'data/place_photo_subject_reviews.json').read_text(encoding='utf-8'))
SPACE_PHOTOS = {
    place['place_id']: {(photo['photo_url'], photo['source_url']) for photo in place['photos'] if photo['subject'] == 'space'}
    for place in REVIEWS['places']
}
# A reviewed portrait must not reappear via another linked venue's gallery.
PEOPLE_PHOTOS = {
    (photo['photo_url'], photo['source_url'])
    for place in REVIEWS['places'] for photo in place['photos'] if photo['subject'] in {'person', 'performance'}
}


def recommended_photo(place_id, photo_url, source_url):
    key = (photo_url, source_url)
    if key in PEOPLE_PHOTOS:
        return False
    allowed = SPACE_PHOTOS.get(place_id)
    return allowed is None or key in allowed
