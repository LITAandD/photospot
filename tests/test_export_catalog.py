"""공개 카탈로그 스냅샷 재현성: 같은 내용이면 행 저장 순서와 무관하게 같은 바이트."""
import hashlib
import json
import sqlite3
from contextlib import closing

import pytest

from pipeline import place_catalog as catalog
from scripts.export_catalog import SCHEMA_VERSION, build_manifest, export, manifest_path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def source(tmp_path, monkeypatch):
    path = tmp_path / 'source.sqlite3'
    monkeypatch.setenv('PLACE_CATALOG_DB', str(path))
    catalog.import_response('seoul', {'elements': [
        {'type': 'node', 'id': n, 'lat': 37.57, 'lon': 126.97 + n * .001,
         'tags': {'name': f'Cafe {n}', 'amenity': 'cafe'}} for n in range(1, 6)]})
    with closing(sqlite3.connect(path)) as conn:
        conn.execute('CREATE TABLE private_profiles (id TEXT)')       # 공개 목록에 없는 테이블은 빠져야 한다
        conn.commit()
    return path


def test_export_is_byte_identical_and_order_independent(source, tmp_path):
    a, b, c = tmp_path / 'a.sqlite3', tmp_path / 'b.sqlite3', tmp_path / 'c.sqlite3'
    export(a)
    export(b, manifest=False)
    assert sha(a) == sha(b)
    # 같은 내용을 반대 순서로 다시 넣어도 결과는 같다
    with closing(sqlite3.connect(source)) as conn:
        rows = conn.execute('SELECT * FROM region_places').fetchall()
        conn.execute('DELETE FROM region_places')
        conn.executemany('INSERT INTO region_places VALUES (?,?)', reversed(rows))
        conn.commit()
    export(c)
    assert sha(c) == sha(a)
    with closing(sqlite3.connect(a)) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert 'private_profiles' not in tables and 'places' in tables
    export(a)                                                     # 기존 스냅샷 위에 다시 내보내도 같다
    assert sha(a) == sha(b)


def test_manifest_describes_snapshot_without_modifying_it(source, tmp_path):
    out = tmp_path / 'places.sqlite3'
    export(out)
    before = sha(out)
    manifest = json.loads(manifest_path(out).read_text(encoding='utf-8'))
    assert manifest_path(out).name == 'places.manifest.json'
    assert manifest['sha256'] == before and manifest['schema_version'] == SCHEMA_VERSION
    assert manifest['tables']['places'] == 5 and manifest['tables']['region_places'] == 5
    assert manifest['imports']['seoul']['count'] == 5 and manifest['source_timestamps']['places']['fetched_at']
    assert 'official_place_hours.json' in manifest['pipeline_data_sha256']
    assert build_manifest(out) == manifest and sha(out) == before


def test_export_refuses_foreign_destination(source, tmp_path):
    foreign = tmp_path / 'foreign.sqlite3'
    with closing(sqlite3.connect(foreign)) as conn:
        conn.execute('CREATE TABLE users (id TEXT)')
        conn.commit()
    with pytest.raises(ValueError):
        export(foreign)
    with closing(sqlite3.connect(foreign)) as conn:
        assert conn.execute("SELECT name FROM sqlite_master").fetchall() == [('users',)]


def test_manifest_source_hashes_are_portable_across_windows_and_linux(source, tmp_path):
    out = tmp_path / 'places.sqlite3'
    export(out)
    data = tmp_path / 'data'
    data.mkdir()
    metadata = data / 'source.json'
    metadata.write_bytes(b'{\n  "name": "place"\n}\n')
    linux = build_manifest(out, data)
    metadata.write_bytes(b'{\r\n  "name": "place"\r\n}\r\n')
    windows = build_manifest(out, data)
    assert windows == linux and windows['pipeline_data_hash_format'] == 'utf8-lf'
