"""Reviewed space galleries: keep people as context, exclude people as the subject.

Busy venue categories can contain entire artist/event albums. Venues with a full
space-only review hide new photos until reviewed. Partial reviews elsewhere remove
people/event subjects identified in the image or explicit source descriptions.
Import records stay intact for provenance;
all public photo readers apply this policy.
"""
import json
from pathlib import Path
from .photo_identity import source_key
from .photo_viewpoints import bird_view


REVIEWS = json.loads((Path(__file__).parent / 'data/place_photo_subject_reviews.json').read_text(encoding='utf-8'))
SPACE_PHOTOS = {
    place['place_id']: {(photo['photo_url'], photo['source_url']) for photo in place['photos'] if photo['subject'] == 'space'}
    for place in REVIEWS['places']
}
# Partial reviews outside COEX exclude individual assets without hiding the
# unreviewed space photos of an entire venue.
REVIEWED_PHOTOS = [photo for place in REVIEWS['places'] for photo in place['photos']] + REVIEWS.get('photos', [])
# A reviewed portrait must not reappear via another linked venue's gallery.
PEOPLE_PHOTOS = {
    (photo['photo_url'], photo['source_url'])
    for photo in REVIEWED_PHOTOS if photo['subject'] in {'person', 'performance'}
}


PEOPLE_SOURCES = {key for _, source in PEOPLE_PHOTOS if (key := source_key(source)) is not None}
PEOPLE_URLS = {url for url, _ in PEOPLE_PHOTOS}


def recommended_photo(place_id, photo_url, source_url, title='', description=''):
    key = (photo_url, source_url)
    if bird_view(photo_url, source_url, title, description):
        return False
    if photo_url in PEOPLE_URLS or source_key(source_url) in PEOPLE_SOURCES:
        return False
    allowed = SPACE_PHOTOS.get(place_id)
    return allowed is None or key in allowed
