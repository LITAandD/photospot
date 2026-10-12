"""Catalog photos as served to people: only images with a reusable licence by default.

Official brand/shop photos (e.g. '© Starbucks Korea') carry no reuse grant. They stay
in the catalog for provenance but are shown only when ALLOW_OFFICIAL_BRAND_PHOTOS=1,
which an operator may set only after obtaining written permission from the owner.
"""
import os

from pipeline import catalog_photos

REUSABLE_LICENSE_URLS = ('https://creativecommons.org/', 'https://www.gnu.org/licenses/')


def brand_photos_allowed() -> bool:
    return os.environ.get('ALLOW_OFFICIAL_BRAND_PHOTOS') == '1'


def reusable(photo: dict) -> bool:
    return (photo.get('license_url') or '').startswith(REUSABLE_LICENSE_URLS)


def photos_for(ids) -> dict[str, list[dict]]:
    result = catalog_photos.photos_for(ids)
    if brand_photos_allowed():
        return result
    return {pid: kept for pid, photos in result.items() if (kept := [p for p in photos if reusable(p)])}


def photo_counts_for(ids) -> dict[str, int]:
    if brand_photos_allowed():
        return catalog_photos.photo_counts_for(ids)
    ids, counts = list(ids), {}
    for start in range(0, len(ids), 400):   # Bounded SQLite parameter lists.
        counts.update({pid: len(photos) for pid, photos in photos_for(ids[start:start + 400]).items()})
    return counts
