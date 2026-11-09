"""pip-audit 예외 목록: 검토 기한·핀 일치·필드 누락을 검사하고, 오류가 있으면 어떤 예외도 넘기지 않는다."""
from datetime import date
import json

from scripts import check_python_audit as audit

TODAY = date(2026, 11, 9)


def entry(**patch):
    return {'id': 'PYSEC-2026-0001', 'package': 'pillow', 'version': '13.0.0', 'reviewed_at': '2026-11-01',
            'review_after': '2026-12-01', 'rationale': '요청 경로에서 쓰지 않는 디코더', 'mitigation': '호스트 허용 목록', **patch}


def policy(*entries):
    return {'schema_version': 1, 'exceptions': list(entries)}


def test_valid_exception_becomes_ignore_argument():
    ids, errors = audit.validate(policy(entry(), entry(id='CVE-2026-12345', package='certifi', version='2026.10.18')),
                                 {'pillow': '13.0.0', 'certifi': '2026.10.18'}, TODAY)
    assert errors == [] and ids == ['CVE-2026-12345', 'PYSEC-2026-0001']


def test_expired_future_long_or_mismatched_exceptions_are_rejected():
    pins = {'pillow': '13.0.0'}
    for patch in [{'review_after': '2026-11-09'}, {'reviewed_at': '2026-11-10'}, {'review_after': '2027-01-01'},
                  {'version': '12.3.0'}, {'id': 'GHSA-bad'}, {'rationale': ''}, {'package': 'numpy', 'version': '2.5.3'}]:
        ids, errors = audit.validate(policy(entry(**patch)), pins, TODAY)
        assert errors and ids == [], patch
    ids, errors = audit.validate(policy(entry(), entry()), pins, TODAY)
    assert any('Duplicate' in e for e in errors) and ids == []
    # 한 항목이라도 틀리면 유효한 항목도 쓰지 않는다
    ids, errors = audit.validate(policy(entry(), entry(id='CVE-2026-1', version='1')), pins, TODAY)
    assert errors and ids == []


def test_cli_prints_arguments_and_fails_on_invalid_policy(tmp_path, capsys):
    constraints = tmp_path / 'constraints.txt'
    constraints.write_text('pillow==13.0.0\n', encoding='utf-8')
    good = tmp_path / 'good.json'
    good.write_text(json.dumps(policy(entry())), encoding='utf-8')
    args = ['--constraints', str(constraints), '--today', '2026-11-09']
    assert audit.main(['--policy', str(good), '--ignore-args', *args]) == 0
    assert capsys.readouterr().out.strip() == '--ignore-vuln PYSEC-2026-0001'
    bad = tmp_path / 'bad.json'
    bad.write_text(json.dumps(policy(entry(review_after='2026-11-01'))), encoding='utf-8')
    assert audit.main(['--policy', str(bad), '--ignore-args', *args]) == 1
    out = capsys.readouterr()
    assert out.out == '' and 'Expired' in out.err


def test_shipped_policy_is_valid_today_and_pins_are_readable():
    assert audit.main([]) == 0
    assert audit.pins()['pillow'] == '13.0.0'
