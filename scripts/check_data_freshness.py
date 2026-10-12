"""배포 자료(pipeline/data)의 만료일 점검. 네트워크를 쓰지 않고 파일만 읽는다.

  python -m scripts.check_data_freshness                  # 보고만 (항상 0으로 종료)
  python -m scripts.check_data_freshness --fail-within 3  # 3일 안에 만료되는 자료가 있으면 1로 종료
  python -m scripts.check_data_freshness --json
  python -m scripts.check_data_freshness --source official_place_hours --fail-within 0

만료 기준은 앱 조회 규칙과 같다.
- 공식 지점 날짜별 시간: 게시된 마지막 날짜가 지나면 쓰지 않음 (official_place_hours.hours_for)
- 네이버 확인 영업시간: 확인 후 30일 (place_hours.hours_for)
- 카페 인기 신호: 리뷰순 순위 30일, 리뷰·게시물 수 90일 (cafe_popularity.popularity_for)
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import sys

DATA = Path(__file__).resolve().parents[1] / 'pipeline' / 'data'
SOURCES = ('official_place_hours', 'place_hours', 'cafe_popularity')


def _rows(name, data_dir):
    path = Path(data_dir) / name
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []


def expiries(data_dir=DATA):
    """자료별 (항목 수, 확인일 범위, 만료일 목록)."""
    out = {}
    official = _rows('official_place_hours.json', data_dir)
    out['official_place_hours'] = ([r['checked_at'] for r in official],
                                   [date.fromisoformat(max(r['date_hours'])) for r in official])
    reviewed = _rows('place_hours.json', data_dir)
    out['place_hours'] = ([r['checked_at'] for r in reviewed],
                          [date.fromisoformat(r['checked_at']) + timedelta(days=30) for r in reviewed])
    popularity = _rows('cafe_popularity.json', data_dir)
    out['cafe_popularity'] = ([r['checked_at'] for r in popularity],
                              [date.fromisoformat(r['checked_at'])
                               + timedelta(days=30 if r['metric'] == 'naver_local_rank' else 90) for r in popularity])
    return out


def report(today, data_dir=DATA):
    rows = []
    for name, (checked, expiry) in expiries(data_dir).items():
        if not expiry:
            rows.append({'source': name, 'entries': 0})
            continue
        first = min(expiry)
        rows.append({'source': name, 'entries': len(expiry), 'checked_from': min(checked), 'checked_to': max(checked),
                     'first_expiry': first.isoformat(), 'last_expiry': max(expiry).isoformat(),
                     'days_left': (first - today).days, 'expired': sum(e < today for e in expiry)})
    return rows


def main(argv=None):
    from pipeline.catalog_visitors import today as kst_today
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--fail-within', type=int, metavar='DAYS',
                    help='이 일수 안에 만료(또는 이미 만료)되는 자료가 있으면 종료 코드 1')
    ap.add_argument('--today', type=date.fromisoformat, help='기준일 (기본: 오늘 KST)')
    ap.add_argument('--data-dir', type=Path, default=DATA)
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--source', action='append', choices=SOURCES,
                    help='종료 코드 판정에 사용할 자료 (반복 지정 가능, 생략 시 전체). 보고에는 항상 전체 자료를 표시')
    args = ap.parse_args(argv)
    today = args.today or kst_today()
    rows = report(today, args.data_dir)
    if args.json:
        print(json.dumps({'today': today.isoformat(), 'sources': rows}, ensure_ascii=False, indent=1))
    else:
        for r in rows:
            if not r['entries']:
                print(f"{r['source']}: 항목 없음")
                continue
            state = f"{-r['days_left']}일 전 만료" if r['days_left'] < 0 else f"{r['days_left']}일 남음"
            print(f"{r['source']}: {r['entries']}건, 확인 {r['checked_from']}~{r['checked_to']}, "
                  f"가장 빠른 만료 {r['first_expiry']} ({state}), 만료 {r['expired']}건")
    if args.fail_within is not None:
        due = [r['source'] for r in rows if (not args.source or r['source'] in args.source)
               and r['entries'] and r['days_left'] <= args.fail_within]
        if due:
            print(f"갱신 필요 ({args.fail_within}일 기준): {', '.join(due)}", file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
