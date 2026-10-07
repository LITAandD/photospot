"""마이그레이션 실행기: schema.sql → migrations/*.sql 을 이름순으로, 적용된 것은 건너뛴다.

  python -m scripts.migrate            # 적용
  python -m scripts.migrate --seed     # 개발용 예시 데이터까지
  python -m scripts.migrate --status   # 적용 현황만
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
MIGRATION_LOCK = 7264081701


def files() -> list[Path]:
    return [ROOT / "schema.sql"] + sorted((ROOT / "migrations").glob("*.sql"))


def applied_names(conn) -> set[str]:
    if conn.execute("SELECT to_regclass('public.schema_migrations')").fetchone()[0] is None:
        return set()
    return {r[0] for r in conn.execute('SELECT name FROM schema_migrations')}


def run(conn, *, status=False, seed=False, production=False, log=print) -> int:
    if seed and production:
        raise ValueError('운영 DB에는 예시 데이터를 넣을 수 없습니다')
    if status:
        with conn.transaction():
            conn.execute('SET TRANSACTION READ ONLY')
            applied = applied_names(conn)
            pending = [f for f in files() if f.name not in applied]
            for f in files():
                log(f"  {'=' if f.name in applied else '?'} {f.name}")
        return 1 if pending else 0

    # A session lock spans the individual commits. Concurrent deployments cannot race.
    if not conn.execute('SELECT pg_try_advisory_lock(%s)', (MIGRATION_LOCK,)).fetchone()[0]:
        raise ValueError('다른 배포가 마이그레이션 중입니다. 완료 후 다시 실행하세요')
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS schema_migrations (
                        name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())''')
        applied = applied_names(conn)
        for f in files():
            if f.name in applied:
                log(f'  = {f.name}')
                continue
            with conn.transaction():
                conn.execute(f.read_text(encoding='utf-8'))
                conn.execute('INSERT INTO schema_migrations (name) VALUES (%s)', (f.name,))
            log(f'  + {f.name}')
        if seed and 'seed' not in applied:
            with conn.transaction():
                conn.execute((ROOT / 'seed_example.sql').read_text(encoding='utf-8'))
                conn.execute("INSERT INTO schema_migrations (name) VALUES ('seed')")
            log('  + seed_example.sql')
    finally:
        conn.execute('SELECT pg_advisory_unlock(%s)', (MIGRATION_LOCK,))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args(argv)
    production = os.environ.get('APP_ENV') == 'production'
    if args.seed and production:
        ap.error('--seed is forbidden with APP_ENV=production')
    dsn = os.environ.get('DATABASE_URL')
    if not dsn:
        ap.error('DATABASE_URL is required')
    # Autocommit makes each transaction block a real commit, not a nested savepoint.
    try:
        with psycopg.connect(dsn, autocommit=True, connect_timeout=10) as conn:
            return run(conn, status=args.status, seed=args.seed, production=production)
    except psycopg.Error:
        print('DB 연결 또는 마이그레이션 실패. 서버의 접근 제한 로그에서 원인을 확인하세요.', file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
