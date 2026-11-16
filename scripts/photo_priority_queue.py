"""Generate the operational review order from an explicit snapshot copy (no recommendation writes)."""
import argparse
from collections import defaultdict, deque
from datetime import date
import json
import os
from pathlib import Path
import sqlite3

from api.catalog_media import photos_for
from api.preview import browse
from api.public_place_info import ORIGINS
from pipeline.place_catalog import distance_m
from pipeline.place_categories import CATEGORIES, group_for
from pipeline.place_quality import recommendation_exclusion, row_exclusion

CITIES = {'seoul': '서울', 'busan': '부산', 'gangneung': '강릉', 'jeju': '제주'}


def generate(database, visit_date):
    os.environ['PLACE_CATALOG_DB'] = str(database.resolve())
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute('SELECT * FROM places WHERE active=1')]
        members = defaultdict(set)
        for city, pid in conn.execute('SELECT region, place_id FROM region_places'):
            city = city.partition(':')[0]
            if city in CITIES:
                members[pid].add(city)
    covers = photos_for([r['id'] for r in rows])
    first = {city: {i.place_id: rank for rank, i in enumerate(browse(city, visit_date).items, 1)}
             for city in CITIES}
    missing_first = {pid for ranks in first.values() for pid in ranks if pid not in covers}
    buckets = defaultdict(lambda: defaultdict(list))
    first_rows = []
    for r in rows:
        pid = r['id']
        if pid in covers or not members[pid]:
            continue
        if pid not in missing_first and (row_exclusion(r) or recommendation_exclusion(r)):
            continue
        distances = {city: round(distance_m(ORIGINS[city]['lat'], ORIGINS[city]['lng'], r)) for city in members[pid]}
        city = min(distances, key=lambda city: (0 if pid in first[city] else 1, distances[city], city))
        first_rank = first[city].get(pid)
        entry = (distances[city], pid, city, r['name'], r['category'], r['source_url'], first_rank)
        if first_rank:
            first_rows.append(entry)
        else:
            buckets[city][r['category']].append(entry)
    if {r[1] for r in first_rows} != missing_first:
        raise ValueError("First-page candidates are missing from the regional catalog")
    ordered = sorted(first_rows, key=lambda row: (row[6], list(CITIES).index(row[2]), row[1]))
    counts = {c: sum(r[2] == c for r in ordered) for c in CITIES}
    city_lists = {}
    for city in CITIES:
        categories = [deque(sorted(buckets[city][cat])) for cat in sorted(buckets[city])]
        city_lists[city] = deque()
        while any(categories):
            for queue in categories:
                if queue:
                    city_lists[city].append(queue.popleft())
    while len(ordered) < 500:
        for city in CITIES:
            if counts[city] < 125:
                ordered.append(city_lists[city].popleft())
                counts[city] += 1
    assert len({r[1] for r in ordered}) == 500
    sample = Path(__file__).resolve().parents[1] / 'deploy/data/photo_source_sample_200.json'
    follow_up = {r['id']: r['next'] for r in json.loads(sample.read_text('utf8'))['rows']}
    # Jeju catalog lists this dining venue as an attraction. Verify present address before outreach.
    follow_up['98df00a3-2d68-595d-ab27-041256c549bd'] = '현 지점 재확인 후 지점 운영자 제출'
    lines = ['# 미연결 대표사진 확보 우선순위 500곳', '',
             f'{visit_date} 기준 공개 둘러보기 표본과 도시별 분류를 사용한 검수 작업 순서입니다. '
             '최근 30일 운영 노출·상세 조회 기록은 각각 0건입니다. 순번은 이용자 인기 순위가 아닙니다.', '',
             '첫 페이지에 반환된 미연결 장소를 먼저 배치했습니다. 나머지는 네 권역 각 125곳을 채우도록 '
             '카탈로그 분류를 순환하고, 같은 분류 안에서는 도시 기준점과 가까운 지점부터 선정했습니다. '
             '거리는 기준점과 카탈로그 좌표 사이의 직선거리입니다. 같은 이름도 ID를 따로 대조합니다.', '',
             '공공 조사 순서는 국문 관광정보 → 커먼즈 → 서울관광아카이브(서울 대상)입니다. '
             '공공 조사 후에도 자료가 없으면 직접 촬영 후보로 넘깁니다. 시설·음식점 접수는 지점 운영자가 '
             '사용권을 가진 상설 공간 사진을 제출하는 방안입니다. 상세 조사 결과는 [기존 200곳 표본](data/photo_source_sample_200.json)에서 ID로 확인할 수 있습니다.', '',
             '|순번|도시|장소·지도 원출처|카탈로그 ID|유형|거리 m|선정 근거|우선 경로 → 미확보 시|',
             '|---:|---|---|---|---|---:|---|---|']
    for rank, (dist, pid, city, name, cat, url, first_rank) in enumerate(ordered, 1):
        name = name.replace('|', '·').replace('[', '［').replace(']', '］')
        reason = f'첫 페이지 {first_rank}위' if first_rank else '도시·분류 순환'
        if pid in follow_up:
            route = follow_up[pid]
            if route != '직접 촬영 후보':
                route += ' → 직접 촬영'
        elif group_for(cat) == 'cafe':
            route = '지점 운영자 제출 → 직접 촬영'
        elif cat in {'gallery', 'museum', 'event_venue', 'cultural_venue', 'festival_site'}:
            route = '상설 시설 운영자 → 공공 조사·직접 촬영'
        else:
            route = '공공 조사 → 직접 촬영'
        lines.append(f'|{rank}|{CITIES[city]}|[{name}]({url})|{pid}|{CATEGORIES.get(cat, cat)}|{dist}|{reason}|{route}|')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--copy', type=Path, required=True)
    parser.add_argument('--date', type=date.fromisoformat, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.copy.is_file() or args.copy.resolve() == (Path(__file__).resolve().parents[1] / 'catalog/places.sqlite3').resolve():
        parser.error('Supply an existing working copy of the catalog')
    args.output.write_text(generate(args.copy, args.date), encoding='utf8')
