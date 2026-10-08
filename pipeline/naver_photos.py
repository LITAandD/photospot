"""Import manually reviewed, commercially reusable Naver blog space photos.

Search visibility is not permission. Each entry records the primary post's CCL,
author, exact catalog branch and visual review. No network calls at runtime.
"""
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from . import place_catalog as catalog
from .catalog_photos import initialize
from .official_cafe_photos import road_address

MANIFEST = Path(__file__).with_name('data') / 'naver_photos.json'
METHOD = 'licensed:naver'


def canonical_license(value):
    if not isinstance(value, str) or not re.fullmatch(
        r'https://creativecommons\.org/licenses/(?:by|by-sa|by-nd)/(?:2\.0/kr|4\.0)/', value
    ):
        raise ValueError('Explicit commercially reusable CC license required')
    return value


def valid_branch(place, entry):
    try:
        if place['name'] != entry['name'] or catalog.distance_m(entry['lat'], entry['lng'], place) > 75:
            return False
        old, new = road_address(place.get('address')), road_address(entry['address'])
        if old and new and old != new:
            # A reviewed stale OSM address may differ from the primary place page.
            # Pin the old value, require a close source-map match and retain the reason.
            return (place.get('address') == entry.get('catalog_address') and
                    bool(entry.get('address_review')) and
                    catalog.distance_m(entry['lat'], entry['lng'], place) <= 30)
        return not (old and new and old != new)
    except (KeyError, TypeError, ValueError):
        return False


def checked_url(value, hosts):
    u = urlsplit(value)
    if u.scheme != 'https' or u.hostname not in hosts or u.username or u.password or u.port:
        raise ValueError('Invalid photo/source URL')
    return u


def apply(path=None, manifest=MANIFEST):
    entries = json.loads(Path(manifest).read_text(encoding='utf-8'))['places']
    prepared = []
    with catalog.connect(path) as conn:
        for entry in entries:
            row = conn.execute('SELECT * FROM places WHERE id=? AND active=1', (entry['place_id'],)).fetchone()
            if row is None or row['source_url'] != entry['place_source'] or not valid_branch(dict(row), entry):
                raise ValueError('Unmatched photo branch: ' + entry['name'])
            checked = date.fromisoformat(entry['reviewed_at'])
            if checked > date.today(): raise ValueError('Future photo review')
            source = checked_url(entry['source_url'], {'blog.naver.com', 'm.blog.naver.com'})
            if not re.fullmatch(r'/[A-Za-z0-9_-]+/\d+', source.path):
                raise ValueError('Individual source post required')
            license_url = canonical_license(entry['license_url'])
            code, version, *locale = urlsplit(license_url).path.strip('/').split('/')[1:]
            license_name = 'CC ' + code.upper() + ' ' + version + (' KR' if locale else '')
            if entry['license'] != license_name: raise ValueError('License label does not match URL')
            if not entry['author'].strip() or not entry['address'].strip() or not entry.get('license_evidence', '').strip():
                raise ValueError('Missing attribution/address/license review')
            for photo in entry['photos']:
                checked_url(photo['url'], {'postfiles.pstatic.net', 'blogfiles.pstatic.net'})
                if min(photo['width'], photo['height']) < 100 or not photo['spatial_review'].strip():
                    raise ValueError('Unreviewed space photo')
                file_title = 'Naver:' + hashlib.sha256(photo['url'].encode()).hexdigest()[:24]
                prepared.append((row['id'], file_title, photo['url'], photo['url'], entry['source_url'],
                    license_name, license_url, entry['author'], photo['description'], photo['width'], photo['height'],
                    METHOD, json.dumps({k: v for k, v in entry.items() if k != 'photos'}, ensure_ascii=False),
                    5, datetime.now(timezone.utc).isoformat()))
        initialize(conn)
        # Validation precedes the transaction; only this provider's reviewed set is replaced.
        conn.execute('DELETE FROM catalog_photos WHERE match_method=?', (METHOD,))
        conn.executemany('INSERT INTO catalog_photos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', prepared)
    return {'places': len({r[0] for r in prepared}), 'photos': len(prepared)}


if __name__ == '__main__':
    print(json.dumps(apply(), ensure_ascii=False))
