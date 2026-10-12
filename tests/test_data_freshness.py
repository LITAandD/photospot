"""배포 자료 만료 점검, 만료된 공식 시간의 조회 시 처리, 파이프라인의 KST 기준일."""
from datetime import date, timedelta
import json
from pathlib import Path
import re

from pipeline import official_place_hours as official, place_hours
from scripts import check_data_freshness as fresh


def write(tmp_path, checked='2026-10-07'):
    start = date.fromisoformat(checked)
    (tmp_path / 'official_place_hours.json').write_text(json.dumps([{
        'place_id': 'x', 'checked_at': checked,
        'date_hours': {(start + timedelta(days=i)).isoformat(): '08:00–22:00' for i in range(7)}}]), encoding='utf-8')
    (tmp_path / 'place_hours.json').write_text(json.dumps([{'place_id': 'y', 'checked_at': '2026-10-06'}]), encoding='utf-8')
    return tmp_path


def test_report_days_left_and_expired(tmp_path):
    rows = {r['source']: r for r in fresh.report(date(2026, 10, 12), write(tmp_path))}
    assert rows['official_place_hours']['first_expiry'] == '2026-10-13' and rows['official_place_hours']['days_left'] == 1
    assert rows['official_place_hours']['expired'] == 0
    assert rows['place_hours']['days_left'] == 24 and rows['cafe_popularity']['entries'] == 0
    assert {r['source']: r for r in fresh.report(date(2026, 10, 14), tmp_path)}['official_place_hours']['expired'] == 1


def test_exit_code_only_with_flag(tmp_path, capsys):
    write(tmp_path)
    args = ['--data-dir', str(tmp_path), '--today', '2026-10-12']
    assert fresh.main(args) == 0
    assert '1일 남음' in capsys.readouterr().out
    assert fresh.main(args + ['--fail-within', '3']) == 1
    assert fresh.main(args + ['--fail-within', '0']) == 0
    assert fresh.main(['--data-dir', str(tmp_path), '--today', '2026-10-20', '--fail-within', '0']) == 1


def test_shipped_data_is_readable():
    assert {r['source'] for r in fresh.report(date(2026, 10, 12))} == {'official_place_hours', 'place_hours', 'cafe_popularity'}


def test_official_refresh_is_not_blocked_by_unrelated_expired_data(tmp_path, capsys):
    write(tmp_path, checked='2026-11-09')
    args = ['--data-dir', str(tmp_path), '--today', '2026-11-09', '--fail-within', '0']
    assert fresh.main(args) == 1                              # Reviewed hours still need attention.
    capsys.readouterr()
    assert fresh.main(args + ['--source', 'official_place_hours']) == 0
    assert 'place_hours: 1건' in capsys.readouterr().out       # Still visible in the report.
    assert fresh.main(args + ['--source', 'official_place_hours', '--source', 'place_hours']) == 1
    assert fresh.main(['--data-dir', str(tmp_path), '--today', '2026-11-16',
                       '--source', 'official_place_hours', '--fail-within', '0']) == 1


def official_place(**extra):
    return {'id': 'official-test', 'name': '스타벅스 테스트', 'category': 'cafe', 'lat': 37.5, 'lng': 127,
            'address': '테스트로 10', **extra}


def official_entry():
    start = date(2026, 10, 7)
    return official.DatedHours(place_id='official-test', store_id='1234', branch='스타벅스 테스트', lat=37.5, lng=127,
                               address='테스트로 10', checked_at=start,
                               date_hours={start + timedelta(days=i): '08:00–22:00' for i in range(7)})


def test_expired_official_hours_fall_back_to_map_hours(monkeypatch):
    row = official_entry()
    monkeypatch.setattr(official, 'entries', lambda: {row.place_id: row})
    osm = {'opening_hours': 'Mo-Su 07:00-21:00', 'source_url': 'https://www.openstreetmap.org/node/1',
           'fetched_at': '2026-10-06T00:00:00+00:00'}
    current = place_hours.hours_for(official_place(**osm), date(2026, 10, 8), date(2026, 10, 8))
    assert current['provider'] == 'official' and not current['stale']
    expired = place_hours.hours_for(official_place(**osm), date(2026, 10, 15), date(2026, 10, 15))
    assert expired['provider'] == 'openstreetmap' and '07:00' in expired['summary']
    assert '게시 기간이 지나' in expired['notes'][0]
    # 지도 등록시간도 없으면 만료 표시만 하고 지난 주 시간을 쓰지 않는다
    bare = place_hours.hours_for(official_place(), date(2026, 10, 15), date(2026, 10, 15))
    assert bare['provider'] == 'official' and bare['stale'] and '08:00' not in bare['summary']


def test_pipeline_dates_use_kst_not_server_timezone():
    naive = re.compile(r'\bdate\.today\(\)|datetime\.(?:now|today)\(\)|datetime\.utcnow\(')
    root = Path(__file__).resolve().parents[1]
    offenders = [f'{p.relative_to(root)}:{i}' for d in ('pipeline', 'scripts') for p in sorted((root / d).glob('*.py'))
                 for i, line in enumerate(p.read_text(encoding='utf-8').splitlines(), 1) if naive.search(line)]
    assert offenders == []
