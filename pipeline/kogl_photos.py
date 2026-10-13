"""Import visually reviewed, exact-branch KOGL Type 1 space photographs.

The source page must explicitly license the individual photograph. A public
tourism page or a site's general copyright footer alone is not permission.
"""
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from . import place_catalog as catalog
from .catalog_photos import initialize
from .catalog_visitors import today as kst_today
from .naver_photos import checked_url, valid_branch

MANIFEST = Path(__file__).with_name('data') / 'kogl_photos.json'
METHOD = 'licensed:kogl'
LICENSE_URL = 'https://www.kogl.or.kr/info/licenseType1.do'


def apply(path=None, manifest=MANIFEST):
    entries = json.loads(Path(manifest).read_text(encoding='utf-8'))['places']
    prepared = []
    with catalog.connect(path) as conn:
        for entry in entries:
            row = conn.execute('SELECT * FROM places WHERE id=? AND active=1', (entry['place_id'],)).fetchone()
            if row is None or row['source_url'] != entry['place_source'] or not valid_branch(dict(row), entry):
                raise ValueError('Unmatched photo branch: ' + entry['name'])
            if date.fromisoformat(entry['reviewed_at']) > kst_today():
                raise ValueError('Future photo review')
            for index, photo in enumerate(entry['photos']):
                source = checked_url(photo['source_url'], {'www.visitbusan.net'})
                image = checked_url(photo['url'], {'www.visitbusan.net'})
                if (source.path != '/archive/dataSearch/view.nm'
                        or not re.fullmatch(r'dataSid=METADATA\d+', source.query)
                        or not image.path.startswith('/archive/upload/') or image.query or image.fragment):
                    raise ValueError('Individual public archive source and image required')
                if photo['license_url'] != LICENSE_URL or photo['license'] != '공공누리 제1유형':
                    raise ValueError('Only explicitly licensed KOGL Type 1 photos are accepted')
                if (not photo['license_evidence'].strip() or not photo['spatial_review'].strip()
                        or not photo['attribution'].strip() or not photo['description'].strip()
                        or min(photo['width'], photo['height']) < 100):
                    raise ValueError('Missing space/rights review')
                file_title = 'KOGL:' + hashlib.sha256(photo['url'].encode()).hexdigest()[:24]
                prepared.append((row['id'], file_title, photo['url'], photo['url'], photo['source_url'],
                    photo['license'], LICENSE_URL, photo['attribution'], photo['description'],
                    photo['width'], photo['height'], METHOD,
                    json.dumps({k: v for k, v in entry.items() if k != 'photos'}, ensure_ascii=False),
                    5 + index, datetime.now(timezone.utc).isoformat()))
        initialize(conn)
        conn.execute('DELETE FROM catalog_photos WHERE match_method=?', (METHOD,))
        conn.executemany('INSERT INTO catalog_photos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', prepared)
    return {'places': len({r[0] for r in prepared}), 'photos': len(prepared)}


if __name__ == '__main__':
    print(json.dumps(apply(), ensure_ascii=False))
