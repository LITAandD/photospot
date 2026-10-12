"""Export only allowlisted public catalog tables into the deployable snapshot.

같은 입력이면 같은 바이트가 나오게 만든다: 새 파일에 테이블 이름순·기본키순으로 넣고 VACUUM 후 교체.
스냅샷 옆에 manifest(sha256·테이블별 행 수·스키마 버전·원천 자료 시각)를 남긴다.

  python -m scripts.export_catalog                    # storage → catalog/places.sqlite3 + places.manifest.json
  python -m scripts.export_catalog --manifest-only    # 기존 스냅샷은 그대로 두고 manifest만 다시 쓴다
"""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from pipeline import place_catalog

PUBLIC_TABLES = {'places', 'region_places', 'imports', 'catalog_photos', 'photo_imports', 'catalog_visuals', 'cafe_popularity', 'catalog_visitors', 'catalog_annual_visitors', 'catalog_descriptions', 'catalog_instagram'}
SCHEMA_VERSION = 1      # 공개 테이블 구조가 바뀌면 올린다 (PRAGMA user_version)
TIME_COLUMNS = ('fetched_at', 'source_updated_at', 'completed_at', 'checked_at', 'retrieved_at', 'published_at')
DATA_DIR = place_catalog.ROOT / 'pipeline' / 'data'


def _q(name):
    return '"' + name.replace('"', '""') + '"'


def _order_by(conn, name):
    cols = conn.execute(f'PRAGMA table_info({_q(name)})').fetchall()
    pk = [c[1] for c in sorted(cols, key=lambda c: c[5]) if c[5]]
    return ','.join(_q(c) for c in (pk or [c[1] for c in cols]))          # 기본키 없으면 전 열


def manifest_path(destination):
    destination = Path(destination)
    return destination.with_name(destination.stem + '.manifest.json')


def export(destination=None, manifest=True):
    destination = Path(destination or place_catalog.ROOT / 'catalog' / 'places.sqlite3')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        with closing(sqlite3.connect(destination)) as existing:
            tables = {r[0] for r in existing.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables - PUBLIC_TABLES - {'sqlite_sequence'}:
            raise ValueError('Destination contains non-catalog tables')
    pending = destination.with_name(destination.name + '.tmp')
    pending.unlink(missing_ok=True)
    try:
        with place_catalog.connect() as source, closing(sqlite3.connect(pending)) as target:
            for name, sql in source.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
                if name not in PUBLIC_TABLES: continue
                target.execute(sql)
                rows = source.execute(f'SELECT * FROM {_q(name)} ORDER BY {_order_by(source, name)}')
                width = len(rows.description)
                target.executemany(f'INSERT INTO {_q(name)} VALUES ({",".join("?" * width)})', rows)
            if not target.execute('SELECT count(*) FROM places WHERE active=1').fetchone()[0]:
                raise ValueError('Cannot publish an empty catalog')
            target.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
            target.commit()
            target.execute('VACUUM')
            assert target.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        os.replace(pending, destination)
    finally:
        pending.unlink(missing_ok=True)
    if manifest: write_manifest(destination)
    print('Public catalog exported: ' + str(destination))


def build_manifest(db, data_dir=DATA_DIR):
    """스냅샷을 읽기 전용으로 열어 요약한다 (파일을 바꾸지 않는다)."""
    db = Path(db)
    digest = hashlib.sha256(db.read_bytes()).hexdigest()
    with closing(sqlite3.connect(f'file:{db.resolve().as_posix()}?mode=ro&immutable=1', uri=True)) as conn:
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        schema = conn.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        tables, sources = {}, {}
        for name, _ in schema:
            tables[name] = conn.execute(f'SELECT count(*) FROM {_q(name)}').fetchone()[0]
            cols = {c[1] for c in conn.execute(f'PRAGMA table_info({_q(name)})')}
            latest = {c: conn.execute(f'SELECT max({_q(c)}) FROM {_q(name)}').fetchone()[0] for c in TIME_COLUMNS if c in cols}
            if any(latest.values()): sources[name] = {c: v for c, v in latest.items() if v}
        imports = {r[0]: {'fetched_at': r[1], 'source_updated_at': r[2], 'count': r[3]} for r in conn.execute(
            'SELECT region, fetched_at, source_updated_at, count FROM imports ORDER BY region')} if 'imports' in tables else {}
    data = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(data_dir).glob('*.json'))}
    return {'file': db.name, 'sha256': digest, 'bytes': db.stat().st_size, 'schema_version': version,
            'schema_sha256': hashlib.sha256('\n'.join(f'{n}\n{s}' for n, s in schema).encode()).hexdigest(),
            'tables': tables, 'source_timestamps': sources, 'imports': imports, 'pipeline_data_sha256': data}


def write_manifest(db, out=None):
    out = Path(out or manifest_path(db))
    out.write_text(json.dumps(build_manifest(db), ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('destination', nargs='?')
    ap.add_argument('--manifest-only', action='store_true')
    args = ap.parse_args()
    if args.manifest_only:
        print('Manifest written: ' + str(write_manifest(args.destination or place_catalog.ROOT / 'catalog' / 'places.sqlite3')))
    else:
        export(args.destination)
