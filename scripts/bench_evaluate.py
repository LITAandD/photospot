"""/preview/evaluate CPU 벤치마크(F005): 카탈로그 사본으로 반경별 요청당 CPU 시간과 응답 크기를 잰다.

  python -m scripts.bench_evaluate                  # 1·5·50km, 각 5회 중앙값 (장소별 캐시는 두 번째 요청부터 적중)
  python -m scripts.bench_evaluate --hooks          # ranking-data 호출부가 api.scoring_cache를 쓸 때의 수치를 몽키패치로 미리 본다
  python -m scripts.bench_evaluate --verify         # 캐시 적중 전·후, 훅 적용 전·후의 응답 JSON이 같은지 확인
  python -m scripts.bench_evaluate --profile 5000   # cProfile 상위 함수

좋아요 저장소(DATABASE_URL)는 끄고 잰다: 네트워크 왕복이 아니라 랭킹 CPU만 본다.
"""
import argparse
import cProfile
import gzip
import io
import json
import logging
import os
from pathlib import Path
import pstats
import shutil
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PROFILE = {'gender': 'female', 'height_cm': 165, 'pc_season': 'summer_cool', 'body_type': 'natural', 'mbti': 'ENFP'}


def request(radius_m, place_ids=()):
    return {'profile': PROFILE, 'lat': 37.5796, 'lng': 126.977, 'visit_date': '2026-11-09',
            'radius_m': radius_m, 'place_ids': list(place_ids)}


def prepare(catalog):
    """카탈로그 사본을 임시 폴더에 두고(저장소 파일은 건드리지 않는다) 앱을 띄운다."""
    workdir = Path(tempfile.mkdtemp(prefix='photospot-bench-'))
    copy = workdir / 'places.sqlite3'
    shutil.copyfile(catalog, copy)
    os.environ['PLACE_CATALOG_DB'] = str(copy)
    os.environ['RATE_LIMIT_PREVIEW_PER_MIN'] = '0'
    os.environ.pop('DATABASE_URL', None)
    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient
    from api.preview import app
    logging.getLogger('photospot').setLevel(logging.WARNING)
    return TestClient(app), workdir


def apply_hooks():
    """제안한 호출부 변경을 미리 적용한다(저장소 파일은 그대로). requests_for_other_owners 참고."""
    import unicodedata
    from api import catalog_recommendations as R, scoring_cache as cache
    from pipeline import catalog_mbti as mbti, place_catalog as catalog
    from pipeline.place_categories import group_for
    dc, sn = mbti.description_character, mbti.space_nature
    mbti.description_character = lambda d: cache.memo('bench:dc', tuple((x['source_url'], x['checked_at']) for x in d or ()), lambda: dc(d))
    mbti.space_nature = lambda p: cache.memo('bench:sn', p['id'], lambda: sn(p)) if p and p.get('id') else sn(p)
    R.resolve_elements = cache.elements_for
    name = R.public_name
    R.public_name = lambda p: cache.memo('bench:name', p['id'], lambda: name(p))

    def unique_places(entries, photos=None):   # R.unique_places에 NearbyIndex를 끼운 판
        photos = photos or {}
        index, seen_keys = cache.NearbyIndex(), set()
        for entry in entries:
            place = entry[0]
            tags = place.get('tags') or {}
            if isinstance(tags, str): tags = json.loads(tags)
            keys = [('wikidata', tags['wikidata'])] if tags.get('wikidata') else []
            if len(photos.get(place['id'], [])) >= 2:
                keys.append(('gallery', tuple(sorted(p['url'] for p in photos[place['id']]))))
            if any(key in seen_keys for key in keys):
                continue
            group, name = group_for(place['category']), ''.join(unicodedata.normalize('NFKC', R.public_name(place)).split()).casefold()
            reach = 1000 if place['category'] in {'waterfront', 'scenic'} or R.LINEAR.search(place['name'].strip()) else 150
            if any((other_name == name or (len(min(name, other_name, key=len)) >= 2 and
                    (name.startswith(other_name) or other_name.startswith(name))))
                   and catalog.distance_m(other['lat'], other['lng'], place) <= (reach if other_name == name else 150)
                   for other_name, other in index.near(group, place, reach)):
                continue
            index.add(group, name, place)
            seen_keys.update(keys)
            yield entry
    R.unique_places = unique_places


def measure(client, radius_m, runs):
    cpu, wall = [], []
    for _ in range(runs):
        t0, c0 = time.perf_counter(), time.process_time()
        response = client.post('/preview/evaluate', json=request(radius_m))
        wall.append(time.perf_counter() - t0)
        cpu.append(time.process_time() - c0)
    response.raise_for_status()
    data = response.json()
    raw = json.dumps(data, ensure_ascii=False).encode()
    items = data['recommendations']['items']
    metrics = sum(len(json.dumps(i['scoring']['metrics'], ensure_ascii=False).encode()) for i in items if i.get('scoring'))
    return {'radius_m': radius_m, 'cpu_s': round(statistics.median(cpu), 3), 'wall_s': round(statistics.median(wall), 3),
            'items': len(items), 'bytes': len(raw), 'gzip_bytes': len(gzip.compress(raw, 5)),
            'metrics_share': round(metrics / len(raw), 2)}


def verify(client):
    """같은 요청을 캐시가 비었을 때와 찼을 때, 훅 적용 전후로 보내 응답이 같은지 본다."""
    from api import scoring_cache
    results = {}
    for radius_m in (1000, 5000, 50000):
        scoring_cache.clear()
        cold = client.post('/preview/evaluate', json=request(radius_m)).json()
        warm = client.post('/preview/evaluate', json=request(radius_m)).json()
        detail = [i['place_id'] for i in cold['recommendations']['items'][:3]]
        cold_detail = client.post('/preview/evaluate', json=request(radius_m, detail)).json()
        results[radius_m] = (cold, warm, cold_detail)
        assert cold == warm, f'{radius_m}m: 캐시 적중 후 응답이 다르다'
    apply_hooks()
    for radius_m, (cold, _, cold_detail) in results.items():
        hooked = client.post('/preview/evaluate', json=request(radius_m)).json()
        assert hooked == cold, f'{radius_m}m: 훅 적용 후 응답이 다르다'
        detail = [i['place_id'] for i in cold['recommendations']['items'][:3]]
        assert client.post('/preview/evaluate', json=request(radius_m, detail)).json() == cold_detail
    print('verified: identical responses with warm cache and with hooks (1km, 5km, 50km, detail)')


def profile(client, radius_m):
    client.post('/preview/evaluate', json=request(radius_m))
    profiler = cProfile.Profile()
    profiler.enable()
    client.post('/preview/evaluate', json=request(radius_m))
    profiler.disable()
    out = io.StringIO()
    pstats.Stats(profiler, stream=out).sort_stats('tottime').print_stats(25)
    print('\n'.join(line for line in out.getvalue().splitlines() if line.strip()))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--catalog', default=str(ROOT / 'catalog' / 'places.sqlite3'))
    ap.add_argument('--radii', default='1000,5000,50000')
    ap.add_argument('--runs', type=int, default=5)
    ap.add_argument('--hooks', action='store_true')
    ap.add_argument('--verify', action='store_true')
    ap.add_argument('--profile', type=int, metavar='RADIUS_M')
    args = ap.parse_args(argv)
    client, workdir = prepare(args.catalog)
    try:
        if args.verify:
            verify(client)
            return
        if args.hooks:
            apply_hooks()
        if args.profile:
            profile(client, args.profile)
            return
        client.post('/preview/evaluate', json=request(5000))        # 모듈 로드·첫 연결은 재지 않는다
        for radius_m in (int(r) for r in args.radii.split(',')):
            print(json.dumps(measure(client, radius_m, args.runs), ensure_ascii=False))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == '__main__':
    main()
