"""Residual review regressions; no network, model downloads or live credentials."""
from datetime import date
import json
import sys
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.main import create_app
from api import schemas
from pipeline import masking, official_place_hours as hours
from scripts.check_dependencies import check


def test_api_limit_precedes_auth_and_database_access():
    app = create_app(Settings(rate_limit_api_per_min=2, rate_limit_auth_per_min=60))
    with TestClient(app) as client:
        assert client.get('/v1/me/profile').status_code == 401
        assert client.get('/v1/me/profile').status_code == 401
        response = client.get('/v1/me/profile', headers={'Origin': 'http://localhost:8081'})
        assert response.status_code == 429 and int(response.headers['retry-after']) > 0
        assert response.headers['access-control-allow-origin'] == 'http://localhost:8081'
        assert client.get('/health').status_code != 429


def test_birth_validation_uses_korean_date_at_utc_year_boundary(monkeypatch):
    monkeypatch.setattr(schemas, 'kst_today', lambda: date(2027, 1, 1))
    assert schemas.Profile(birth_year=2027).birth_year == 2027
    assert schemas.SajuIn(birth_date='2027-01-01', consent=True).birth_date == '2027-01-01'
    with pytest.raises(ValueError):
        schemas.SajuIn(birth_date='2027-01-02', consent=True)


def test_masking_background_polarity_and_threshold_without_model(monkeypatch):
    image = Image.new('RGBA', (3, 2), (50, 70, 90, 255))
    plain = masking.NoMask().background_mask(image)
    assert plain.shape == (2, 3) and plain.dtype == bool and plain.all()
    def remove(rgb, *, session, only_mask):
        assert rgb.mode == 'RGB' and session == 'session' and only_mask
        return Image.fromarray(np.array([[0, 127, 128], [255, 10, 200]], dtype=np.uint8))
    monkeypatch.setitem(sys.modules, 'rembg', SimpleNamespace(new_session=lambda model: 'session', remove=remove))
    result = masking.get_masker('rembg').background_mask(image)
    assert result.tolist() == [[True, True, False], [False, True, False]]


def test_hours_refresh_removes_only_retired_places_and_keeps_failed_active_rows(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from functools import lru_cache
    observed = hours.datetime.now(hours.ZoneInfo('Asia/Seoul')).date()
    def row(pid):
        return hours.DatedHours(place_id=pid, store_id='1234', branch='스타벅스 테스트', lat=37.5,
                               lng=127, address='테스트로 10', checked_at=observed,
                               date_hours={observed: '08:00–22:00'})
    @lru_cache
    def entries():
        return {pid: row(pid) for pid in ['active', 'retired']}
    class Client:
        def __init__(self): self.cache = tmp_path / 'cache'; self.cache.mkdir(exist_ok=True)
        def post(self, action, params): raise OSError('temporarily unavailable')
    @contextmanager
    def connect():
        yield SimpleNamespace(execute=lambda sql: [{'id': 'active'}])
    monkeypatch.setattr(hours, 'entries', entries)
    monkeypatch.setattr(hours, 'DATA', tmp_path / 'hours.json')
    monkeypatch.setattr(hours.official, 'Client', Client)
    monkeypatch.setattr(hours.catalog, 'ROOT', tmp_path)
    monkeypatch.setattr(hours.catalog, 'connect', connect)
    monkeypatch.setattr(hours.official, 'match_branches', lambda *args: {'active': {'s_biz_code': '1234'}})
    result = hours.run(allow_retire=True)
    assert result['retired'] == ['retired'] and len(result['failures']) == 1
    assert [r['place_id'] for r in json.loads(hours.DATA.read_text(encoding='utf-8'))] == ['active']


def test_dependency_pins_are_checked_and_drift_is_rejected(tmp_path):
    check()
    (tmp_path / 'constraints.txt').write_text('fastapi==1.2.3\n')
    (tmp_path / 'requirements.txt').write_text('fastapi>=1\n')
    (tmp_path / 'pyproject.toml').write_text('[project]\ndependencies=["fastapi==1.2.4"]\n')
    with pytest.raises(ValueError, match='differs'):
        check(tmp_path)


def test_shipped_catalog_manifest_matches_snapshot_and_reviewed_sources():
    from pathlib import Path
    from scripts.export_catalog import build_manifest
    root = Path(__file__).resolve().parents[1]
    actual = build_manifest(root / 'catalog/places.sqlite3')
    expected = json.loads((root / 'catalog/places.manifest.json').read_text(encoding='utf-8'))
    assert actual == expected, 'Regenerate with python -m scripts.export_catalog --manifest-only'
