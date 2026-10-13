"""Stable public photo identity, independent of thumbnail size and place ranking."""
import hashlib


def photo_id(photo):
    return hashlib.sha256(((photo.get('source_url') or '') + '\n' +
                           (photo.get('original_url') or photo['url'])).encode()).hexdigest()
