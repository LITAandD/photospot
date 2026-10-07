"""The hosted preview must run without production credentials or a writable bundle."""
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_hosted_preview_uses_public_snapshot_and_stateless_calculations():
    env = {key: value for key, value in os.environ.items()
           if key not in {"DATABASE_URL", "JWT_SECRET", "PLACE_CATALOG_DB"}}
    result = subprocess.run([sys.executable, "-c", r'''
import hashlib
from pathlib import Path
from fastapi.testclient import TestClient

source = Path('catalog/places.sqlite3')
before = hashlib.sha256(source.read_bytes()).hexdigest()
from deploy.vercel.index import app, _catalog_path
assert _catalog_path.resolve() != source.resolve()
with TestClient(app) as client:
    assert client.get('/health').json() == {'ok': True, 'mode': 'personal-preview'}
    result = client.post('/preview/evaluate', json={
        'profile': {}, 'lat': 37.5796, 'lng': 126.977,
        'visit_date': '2026-10-07', 'radius_m': 5000,
    })
    assert result.status_code == 200, result.text
    assert result.json()['recommendations']['items']
    assert result.headers['cache-control'] == 'no-store'
    saju = client.post('/preview/saju', json={'birth_date': '1993-08-21', 'consent': True})
    assert saju.status_code == 200, saju.text
    assert abs(sum(saju.json()['percents'].values()) - 100) < 0.5
    rejected = client.post('/preview/saju', json={'birth_date': '1993-99-99', 'consent': True})
    assert rejected.status_code == 422 and '1993-99-99' not in rejected.text
    assert client.get('/openapi.json').status_code == 404
assert hashlib.sha256(source.read_bytes()).hexdigest() == before
'''], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
