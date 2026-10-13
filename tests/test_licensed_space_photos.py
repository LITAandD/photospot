"""Keep the licensed replacements on the actual public preview response path."""
import json
from pathlib import Path
import shutil
import sqlite3

from api.catalog_media import photos_for, photo_counts_for, reusable
from api.preview import app
from fastapi.testclient import TestClient


def test_all_instagram_branches_have_reusable_direct_photos(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    db = tmp_path / 'public.sqlite3'
    shutil.copyfile(root / 'catalog/places.sqlite3', db)
    monkeypatch.setenv('PLACE_CATALOG_DB', str(db))
    monkeypatch.delenv('ALLOW_OFFICIAL_BRAND_PHOTOS', raising=False)
    with sqlite3.connect(db) as conn:
        ids = [r[0] for r in conn.execute('SELECT DISTINCT place_id FROM catalog_instagram')]
    assert len(ids) == 16
    photos = photos_for(ids)
    assert set(photos) == set(ids)
    assert photo_counts_for(ids) == {pid: len(ps) for pid, ps in photos.items()}
    for ps in photos.values():
        assert all(reusable(p) and p['attribution'] and p['source_url'] for p in ps)
        assert all('instagram.com' not in p['url'] and 'cdninstagram.com' not in p['url'] for p in ps)
    with TestClient(app) as client:
        for requested, gallery in [(ids, False), *[([pid], True) for pid in ids]]:
            response = client.post('/preview/evaluate', json={
                'visit_date': '2026-10-13', 'profile': {}, 'place_ids': requested,
                'include_gallery': gallery,
            })
            assert response.status_code == 200, response.text
            data = response.json()
            assert set(data['places']) == set(requested)
            for pid, detail in data['places'].items():
                expected = photos[pid] if gallery else photos[pid][:1]
                assert [p['url'] for p in detail['photos']] == [p['url'] for p in expected]


def test_embed_execution_is_not_allowed_by_hosted_web_policy():
    config = json.loads((Path(__file__).resolve().parents[1] / 'vercel.json').read_text(encoding='utf-8'))
    csp = next(h['value'] for rule in config['headers'] for h in rule['headers'] if h['key'] == 'Content-Security-Policy')
    assert "script-src 'self';" in csp and "frame-src 'none';" in csp
    assert 'instagram.com' not in csp
    assert 'https://www.visitbusan.net' in csp.split('img-src ')[1].split(';')[0]
