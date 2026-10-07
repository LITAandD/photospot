"""Read-only server preflight. Default is offline; --database opts into a DB read."""
import argparse
import json
import os
from pathlib import Path

import psycopg
from dotenv import dotenv_values

from api.deployment import server_issues
from scripts.migrate import applied_names, files


def database_issues(dsn):
    issues = []
    try:
        with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as conn:
            with conn.transaction():
                conn.execute('SET TRANSACTION READ ONLY')
                conn.execute("SET LOCAL statement_timeout = '5s'")
                applied = applied_names(conn)
                for file in files():
                    if file.name not in applied:
                        issues.append(f'DB 미적용 마이그레이션: {file.name}')
                if 'seed' in applied:
                    issues.append('DB에 개발용 seed 적용 기록이 있어요. 깨끗한 운영 DB를 준비하세요')
                if not conn.execute("SELECT 1 FROM pg_extension WHERE extname='postgis'").fetchone():
                    issues.append('DB에 PostGIS 확장이 없어요')
    except psycopg.Error:
        # DSNs and provider errors can contain secrets and internal hostnames.
        issues.append('DB 읽기 검사 실패: 접속·읽기 권한·네트워크를 확인하세요 (접속 정보 생략)')
    return issues


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, help='운영 .env 파일; 미지정 시 현재 환경변수만 사용')
    parser.add_argument('--growth', action='store_true', help='Instagram·후원/구독·GPT 설정도 필수 검사')
    parser.add_argument('--database', action='store_true', help='실제 DB에 읽기 전용 접속하여 적용 현황 확인')
    parser.add_argument('--json', action='store_true', help='값/비밀키 없는 JSON 결과')
    args = parser.parse_args(argv)
    if args.env_file and not args.env_file.is_file():
        parser.error('지정한 환경 설정 파일을 찾을 수 없습니다')
    # CI/secrets manager environment takes precedence. Disable .env interpolation.
    env = {**(dotenv_values(args.env_file, interpolate=False) if args.env_file else {}), **os.environ}
    env = {k: v or '' for k, v in env.items()}
    issues = server_issues(env, growth=args.growth)
    apple_path = env.get('APPLE_PRIVATE_KEY_PATH')
    if apple_path and not Path(apple_path).is_file():
        issues.append('APPLE_PRIVATE_KEY_PATH: 이 실행 환경에 읽을 키 파일이 없어요')
    if args.database:
        if env.get('DATABASE_URL'):
            issues.extend(database_issues(env['DATABASE_URL']))
        else:
            issues.append('DATABASE_URL이 없어 DB 검사를 실행하지 않았어요')
    result = {'ok': not issues, 'database_check_requested': args.database, 'issues': issues,
              'note': '설정 유효성 검사입니다. 실제 인증·결제·GPT 호출 및 서명 빌드 검증은 별도입니다.'}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"서버 배포 설정: {len(issues)}개 항목 준비 필요" if issues else '서버 배포 설정 검사 통과')
        for issue in issues:
            print('- ' + issue)
        print(result['note'])
    return 1 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())
