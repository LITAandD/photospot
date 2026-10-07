"""Explicit local photo analysis. No request-time downloads or guessed space tags."""
import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import urllib.request
from urllib.parse import urlsplit, unquote

from PIL import Image
from . import place_catalog as catalog
from .catalog_photos import photos_for, photo_counts_for, UA

REVIEWS = {r['place_id']: r for r in json.loads((Path(__file__).parent / 'data/catalog_photo_reviews.json').read_text(encoding='utf-8'))}


def reviewed_evidence(row):
    result = {**dict(row), 'attributes': json.loads(row['attributes'])}
    review = REVIEWS.get(row['place_id'])
    if review and (review['photo_url'], review['source_url']) == (row['photo_url'], row['source_url']):
        if not review['scene_usable']:
            return None
        result['attributes'].pop('form', None)
        if review['form']:
            result['attributes']['form'] = review['form']
        result['method'] = f"사진 색조 통계 + 대표 사진 형태 검토 ({review['checked_at']})"
    elif 'photo-geometry-' in row['method']:
        # CV contours produce review candidates, not final semantic building tags.
        result['attributes'].pop('form', None)
    return result


def initialize(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS catalog_visuals (
        place_id TEXT PRIMARY KEY, photo_url TEXT NOT NULL, source_url TEXT NOT NULL,
        attributes TEXT NOT NULL, method TEXT NOT NULL, checked_at TEXT NOT NULL)''')


def evidence_for(ids, path=None):
    ids = list(ids)
    if not ids: return {}
    current = photos_for(ids, path)
    result = {}
    with catalog.connect(path) as conn:
        initialize(conn)
        for start in range(0, len(ids), 400):
            batch = ids[start:start+400]
            for row in conn.execute(f"SELECT * FROM catalog_visuals WHERE place_id IN ({','.join('?' for _ in batch)})", batch):
                if any(p['url'] == row['photo_url'] for p in current.get(row['place_id'], [])):
                    observed = reviewed_evidence(row)
                    if observed:
                        result[row['place_id']] = observed
    return result


def store(place_id, photo, attributes, method, path=None):
    from .vision import ENUMS
    allowed = {**ENUMS, 'form': ['linear', 'curved', 'organic', 'volumetric'],
               'setting': ['indoor', 'outdoor', 'mixed'],
               'color_temp': ['warm','neutral','cool'], 'brightness': ['bright_soft','mid','high_contrast'],
               'saturation': ['muted','mid','vivid']}
    if not attributes or any(k not in allowed or v not in allowed[k] for k,v in attributes.items()):
        raise ValueError('Invalid photo attributes')
    with catalog.connect(path) as conn:
        initialize(conn)
        conn.execute('INSERT OR REPLACE INTO catalog_visuals VALUES (?,?,?,?,?,?)',
            (place_id, photo['url'], photo['source_url'], json.dumps(attributes), method, datetime.now(timezone.utc).isoformat()))


def color_attributes(image):
    # These are whole-image color observations, not lighting/people/space inference.
    from .color import load_rgb, analyze_pixels, classify_color_temp, classify_brightness, classify_saturation
    from .config import PipelineConfig
    cfg = PipelineConfig(analysis_max_side=192, palette_k=3)
    stats = analyze_pixels(load_rgb(image, cfg.analysis_max_side), None, cfg)
    return {'color_temp': classify_color_temp(stats,cfg.colors), 'brightness': classify_brightness(stats,cfg.colors),
            'saturation': classify_saturation(stats,cfg.colors)}


def read_photo(url):
    hosts = {'upload.wikimedia.org','thumb.wikimedia.org','cafe24.poxo.com','image.istarbucks.co.kr'}
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in hosts:
        raise ValueError('Unsupported image host')
    cache = catalog.ROOT / 'storage' / 'analysis-photos' / (hashlib.sha256(url.encode()).hexdigest() + '.img')
    if cache.exists():
        return cache.read_bytes()
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=15) as response:
        if urlsplit(response.url).hostname not in hosts:
            raise ValueError('Unsupported redirected image host')
        data = response.read(12*1024*1024+1)
    if len(data)>12*1024*1024:
        raise ValueError('Image too large')
    with Image.open(BytesIO(data)) as image:
        image.verify()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)
    return data


def analyze(limit=200, workers=2):
    from .cafe_photos import reviewed
    from .catalog_geometry import analyze_geometry, METHOD
    reviewed_attrs={entry['place_id']:entry for entry in reviewed()}
    with catalog.connect() as conn:
        rows = conn.execute("SELECT id FROM places WHERE active=1 ORDER BY category='cafe' DESC, row_id").fetchall()
    counts = photo_counts_for(r['id'] for r in rows)
    ids = [r['id'] for r in rows if counts.get(r['id'])][:limit]
    prior, current = evidence_for(ids), photos_for(ids)
    pending = [pid for pid in ids if METHOD not in prior.get(pid, {}).get('method', '')]
    def process(pid):
        photo = current[pid][0]
        manual=reviewed_attrs.get(pid)
        try:
            data = read_photo(photo['url'])
            with Image.open(BytesIO(data)) as image:
                previous = prior.get(pid, {})
                attrs = dict(previous['attributes']) if previous.get('photo_url') == photo['url'] else color_attributes(image)
                attrs.update(analyze_geometry(image))
            manual=reviewed_attrs.get(pid)
            # Observations are tied to this exact image, never to a brand or category.
            method=f'사진 색조 통계 · 윤곽 자동 추정 ({METHOD})'
            if manual and unquote(photo['source_url']).split('/wiki/')[-1].replace('_',' ') == manual['file']:
                attrs.update(manual.get('attributes', {}))
                if manual.get('attributes'): method+=' + 공간 특징 사진 검토'
            return pid, photo, attrs, method, None
        except Exception as error:
            return pid, photo, {}, '', type(error).__name__
    done, failed = 0, 0
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as executor:
        for pid, photo, attrs, method, error in executor.map(process, pending):
            if error:
                failed += 1
                print(f'{pid}: {error}', flush=True)
            else:
                store(pid, photo, attrs, method)
                done += 1
            if (done + failed) % 25 == 0:
                print(f'Analyzed {done}, unavailable {failed}, total {len(pending)}', flush=True)
    return {'analyzed':done,'unavailable':failed,'existing':len(prior)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=200)
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(analyze(args.limit, args.workers)))
