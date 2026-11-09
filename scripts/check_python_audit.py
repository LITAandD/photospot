"""pip-audit 예외 목록(security/python-audit-exceptions.json) 검증과 --ignore-vuln 인자 생성.

  python -m scripts.check_python_audit                 # 예외 목록 검증 (만료·필드 누락·핀 불일치면 종료 코드 1)
  python -m scripts.check_python_audit --ignore-args   # 유효한 예외를 pip-audit --ignore-vuln 인자로 출력
  python -m pip_audit -r requirements.txt $(python -m scripts.check_python_audit --ignore-args)

npm 쪽 security/app-audit-exceptions.json과 같은 원칙: 권고 ID(PYSEC/CVE/GHSA)·패키지·constraints.txt의 정확한 핀·검토일·
재검토 기한(최대 45일)·근거·완화책을 모두 적어야 하고, 기한이 지나거나 핀이 바뀌면 예외는 자동으로 무효가 된다.
개수로 통과시키지 않으며, 수정 버전이 있는 권고는 예외 대신 핀을 올린다.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
import json
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'security' / 'python-audit-exceptions.json'
CONSTRAINTS = ROOT / 'constraints.txt'
MAX_REVIEW_DAYS = 45
ID = re.compile(r'^(PYSEC-\d{4}-\d+|CVE-\d{4}-\d{4,}|GHSA(-[a-z0-9]{4}){3})$')
REQUIRED = ('id', 'package', 'version', 'reviewed_at', 'review_after', 'rationale', 'mitigation')


def pins(path=CONSTRAINTS):
    out = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line = line.split('#', 1)[0].strip()
        if line:
            dep = Requirement(line)
            out[canonicalize_name(dep.name)] = str(dep.specifier).removeprefix('==')
    return out


def _date(value):
    try: return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError: return None


def validate(policy, pinned, today):
    """(ignore_ids, errors). 오류가 하나라도 있으면 어떤 예외도 쓰지 않는다."""
    errors, ids, seen = [], [], set()
    if policy.get('schema_version') != 1 or not isinstance(policy.get('exceptions'), list):
        return [], ['Invalid python audit policy']
    for entry in policy['exceptions']:
        key = f"{entry.get('package')}:{entry.get('id')}"
        missing = [f for f in REQUIRED if not isinstance(entry.get(f), str) or not entry[f].strip()]
        if missing: errors.append(f'Missing review evidence: {key} ({", ".join(missing)})'); continue
        if not ID.match(entry['id']): errors.append(f'Unrecognized advisory id: {key}')
        if key in seen: errors.append(f'Duplicate exception: {key}')
        seen.add(key)
        pin = pinned.get(canonicalize_name(entry['package']))
        if pin != entry['version']: errors.append(f'Pinned version differs from reviewed version: {key} ({pin} != {entry["version"]})')
        reviewed, until = _date(entry['reviewed_at']), _date(entry['review_after'])
        if (not reviewed or not until or reviewed > today or until <= today or until <= reviewed
                or (until - reviewed).days > MAX_REVIEW_DAYS):
            errors.append(f'Expired/invalid review date: {key}')
        ids.append(entry['id'])
    return ([] if errors else sorted(set(ids))), errors


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ignore-args', action='store_true', help='pip-audit --ignore-vuln 인자만 출력')
    ap.add_argument('--policy', type=Path, default=POLICY)
    ap.add_argument('--constraints', type=Path, default=CONSTRAINTS)
    ap.add_argument('--today', type=date.fromisoformat, help='기준일 (기본: 오늘 KST)')
    args = ap.parse_args(argv)
    today = args.today or datetime.now(ZoneInfo('Asia/Seoul')).date()   # CI security 작업은 pipeline 의존성 없이 실행
    policy = json.loads(args.policy.read_text(encoding='utf-8'))
    ids, errors = validate(policy, pins(args.constraints), today)
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    if args.ignore_args:
        print(' '.join(f'--ignore-vuln {i}' for i in ids))
    else:
        print(f'Python audit exceptions valid ({len(ids)} unresolved, reviewed and expiring).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
