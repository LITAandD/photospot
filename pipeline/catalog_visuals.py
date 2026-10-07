"""Explicit local photo analysis. No request-time downloads or guessed space tags."""
import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import urllib.request
from urllib.parse import urlsplit, unquote

from PIL import Image
from . import place_catalog as catalog
from .catalog_photos import photos_for, photo_counts_for, UA


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
                    result[row['place_id']] = {**dict(row), 'attributes': json.loads(row['attributes'])}
    return result


def store(place_id, photo, attributes, method, path=None):
    from .vision import ENUMS
    allowed = {**ENUMS, 'color_temp': ['warm','neutral','cool'], 'brightness': ['bright_soft','mid','high_contrast'],
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


def analyze(limit=200):
    from .cafe_photos import reviewed
    reviewed_attrs={entry['place_id']:entry for entry in reviewed()}
    with catalog.connect() as conn:
        rows = conn.execute("SELECT id FROM places WHERE active=1 ORDER BY category='cafe' DESC, row_id").fetchall()
    counts = photo_counts_for(r['id'] for r in rows)
    ids = [r['id'] for r in rows if counts.get(r['id'])][:limit]
    prior, current = evidence_for(ids), photos_for(ids)
    done, failed = 0, 0
    for pid in ids:
        photo = current[pid][0]
        manual=reviewed_attrs.get(pid)
        if pid in prior:
            if manual and unquote(photo['source_url']).split('/wiki/')[-1].replace('_',' ') == manual['file']:
                store(pid, photo, {**prior[pid]['attributes'], **manual.get('attributes', {})}, '사진 전체 색 통계 · 자동 분석 + 공간 특징 사진 검토')
            continue
        try:
            parsed = urlsplit(photo['url'])
            if parsed.scheme != 'https' or parsed.hostname not in {'upload.wikimedia.org','thumb.wikimedia.org','cafe24.poxo.com','image.istarbucks.co.kr'}:
                raise ValueError('Unsupported image host')
            req = urllib.request.Request(photo['url'], headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=15) as response:
                data = response.read(12*1024*1024+1)
            if len(data)>12*1024*1024: raise ValueError('Image too large')
            with Image.open(BytesIO(data)) as image:
                attrs = color_attributes(image)
            manual=reviewed_attrs.get(pid)
            # Observations are tied to this exact image, never to a brand or category.
            method='사진 전체 색 통계 · 자동 분석'
            if manual and unquote(photo['source_url']).split('/wiki/')[-1].replace('_',' ') == manual['file']:
                attrs.update(manual.get('attributes', {}))
                if manual.get('attributes'): method+=' + 공간 특징 사진 검토'
            store(pid, photo, attrs, method)
            done += 1
        except Exception as error:
            failed += 1
            print(f'{pid}: {type(error).__name__}', flush=True)
        print(f'Analyzed {done}, unavailable {failed}', flush=True)
    return {'analyzed':done,'unavailable':failed,'existing':len(prior)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=200)
    print(json.dumps(analyze(parser.parse_args().limit)))
