import json
import shutil

from fastapi.testclient import TestClient
import pytest

from api.preview import app
from pipeline import tourism_photos as kto


@pytest.mark.parametrize('damage', ['missing', 'unreadable', 'invalid-json', 'wrong-shape', 'one-invalid'])
def test_only_unverifiable_covers_disappear(tmp_path, monkeypatch, damage):
    original = json.loads(kto.MANIFEST.read_text(encoding='utf-8'))
    path = tmp_path / 'reviews.json'
    snapshot = tmp_path / 'places.sqlite3'
    shutil.copyfile(kto.MANIFEST.parents[2] / 'catalog/places.sqlite3', snapshot)
    monkeypatch.setenv('PLACE_CATALOG_DB', str(snapshot))
    monkeypatch.setattr(kto, 'MANIFEST', path)
    target = next(r for r in original if r['place']['name'] == '경포대')
    if damage == 'unreadable':
        path.mkdir()  # read_text raises OSError even when running as root
    elif damage == 'invalid-json':
        path.write_bytes(b'{')
    elif damage == 'wrong-shape':
        path.write_bytes(b'{}')
    elif damage == 'one-invalid':
        path.write_text(json.dumps([None, *(r for r in original if r != target)]), encoding='utf-8')
    kto.reviewed_records.cache_clear()
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            for city in ('gangneung', 'jeju'):
                response = client.get(f'/preview/browse?city={city}&visit_date=2026-11-17')
                assert response.status_code == 200
                covers = [i['cover_photo'] for i in response.json()['items'] if i['cover_photo']]
                assert any('tong.visitkorea.or.kr' not in c['url'] for c in covers)
                assert not any(c['url'] == target['photo']['url'] for c in covers)
                assert any('tong.visitkorea.or.kr' in c['url'] for c in covers) == (damage == 'one-invalid')
    finally:
        kto.reviewed_records.cache_clear()
