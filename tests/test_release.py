"""Release regressions that can run without PostgreSQL or external accounts."""
import io
import uuid
from datetime import date
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from api.auth import CurrentUser, current_user
from api.config import Settings
from api.db import get_conn
from api.main import create_app
from api.schemas import Profile, SajuIn
from api.services import sanitize_photo
from api.tokens import issue_access
from pipeline.tourapi import LocalStorage
from saju.calculator import lunar_to_solar, ForcetellerStyleCalculator

SECRET = 'release-tests-secret-at-least-32-bytes'
USER = str(uuid.uuid4())


class Connection:
    def __init__(self, row=None):
        self.row = row
        self.queries = []

    def cursor(self, **kwargs): return self
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params=()): self.queries.append((sql, params)); return self
    def fetchone(self): return self.row


def request_for(token):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=Settings(jwt_secret=SECRET))),
                           headers={'authorization': 'Bearer ' + token})


@pytest.mark.parametrize('claims', [
    {'sub': USER}, {'sub': USER, 'typ': 'access'},
    {'sub': USER, 'typ': 'refresh', 'iat': 1, 'exp': 9999999999, 'jti': 'x'},
    {'sub': USER, 'typ': 'access', 'iat': 1, 'exp': 2, 'jti': 'x'},
])
def test_incomplete_expired_or_wrong_type_tokens_rejected(claims):
    token = jwt.encode(claims, SECRET, algorithm='HS256')
    conn = Connection((None, True))
    with pytest.raises(HTTPException) as error:
        current_user(request_for(token), conn)
    assert error.value.status_code == 401
    assert not conn.queries


def test_admin_role_checked_in_database_and_unknown_user_not_created():
    token, _ = issue_access(USER, True, Settings(jwt_secret=SECRET))
    assert current_user(request_for(token), Connection((None, False))).is_admin is False
    conn = Connection(None)
    with pytest.raises(HTTPException): current_user(request_for(token), conn)
    assert all('INSERT' not in q[0] for q in conn.queries)


@pytest.mark.parametrize('kwargs', [
    {'jwt_secret': 'short'}, {'jwt_secret': SECRET, 'dev_login': True},
    {'jwt_secret': SECRET, 'cors_origins': ['*']},
    {'jwt_secret': SECRET, 'cors_origins': ['http://localhost:8081']},
])
def test_production_rejects_unsafe_settings(kwargs):
    with pytest.raises(ValueError):
        Settings(environment='production', **{'cors_origins': ['https://photos.test'], **kwargs})


def test_production_accepts_explicit_safe_config():
    Settings(environment='production', jwt_secret=SECRET, cors_origins=['https://photos.test'], dev_login=False)


@pytest.mark.parametrize('profile', [{'birth_year': date.today().year + 1}, {'height_cm': 99}, {'height_cm': 231}, {'pc_subtone': 'light'}, {'mbti': 'ABCD'}])
def test_profile_validation(profile):
    with pytest.raises(ValidationError): Profile(**profile)


def test_optional_profile_and_lunar_february_30():
    assert Profile().pc_season is None
    body = SajuIn(birth_date='2024-02-30', calendar='lunar', consent=True)
    assert lunar_to_solar(body.birth_date) == date(2024, 4, 8)
    assert ForcetellerStyleCalculator().calculate(body.birth_date, None, 'lunar').dominant
    with pytest.raises(ValidationError): SajuIn(birth_date='2024-02-30', calendar='solar', consent=True)
    with pytest.raises(ValidationError): SajuIn(birth_date='2024-02-30', calendar='lunar', leap_month=True, consent=True)


def test_validation_errors_are_json_and_do_not_echo_private_input(tmp_path):
    app = create_app(Settings(jwt_secret=SECRET, storage_root=str(tmp_path)))
    app.dependency_overrides[get_conn] = lambda: Connection()
    app.dependency_overrides[current_user] = lambda: CurrentUser(USER, False)
    with TestClient(app) as client:
        result = client.put('/v1/me/saju', json={'birth_date': '2099-12-31', 'consent': True})
        assert result.status_code == 422
        assert isinstance(result.json()['detail'], str)
        assert '2099-12-31' not in result.text
        assert result.headers['cache-control'] == 'no-store'
        assert result.headers['x-content-type-options'] == 'nosniff'


def test_each_app_has_an_independent_closed_pool():
    a, b = create_app(Settings()), create_app(Settings())
    assert a.state.pool is not b.state.pool
    assert a.state.pool.closed and b.state.pool.closed


def test_private_or_unknown_files_are_not_served(tmp_path):
    storage = LocalStorage(str(tmp_path))
    storage.save('user/private.jpg', b'private')
    app = create_app(Settings(storage_root=str(tmp_path)))
    app.dependency_overrides[get_conn] = lambda: Connection(None)
    with TestClient(app) as client:
        assert client.get('/media/user/private.jpg').status_code == 404


def test_public_photo_served_only_inside_storage_root(tmp_path):
    LocalStorage(str(tmp_path)).save('own/photo.jpg', b'public-photo')
    app = create_app(Settings(storage_root=str(tmp_path)))
    app.dependency_overrides[get_conn] = lambda: Connection((1,))
    with TestClient(app) as client:
        result = client.get('/media/own/photo.jpg')
        assert result.status_code == 200 and result.content == b'public-photo'
        assert client.get('/media/missing.jpg').status_code == 404


@pytest.mark.parametrize('path', ['../outside.jpg', '../../outside.jpg', '/absolute.jpg'])
def test_storage_cannot_escape_root(tmp_path, path):
    storage = LocalStorage(str(tmp_path))
    with pytest.raises(ValueError): storage.save(path, b'data')
    with pytest.raises(ValueError): storage.delete(path)


def test_uploaded_images_strip_gps_and_device_metadata():
    image = Image.new('RGB', (30, 40), '#aabbcc')
    exif = Image.Exif()
    exif[271] = 'Private device name'
    exif[270] = 'Sensitive image description'
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', exif=exif)
    cleaned, _ = sanitize_photo(buffer.getvalue())
    result = Image.open(io.BytesIO(cleaned))
    assert 271 not in result.getexif() and 270 not in result.getexif()
    with pytest.raises(ValueError): sanitize_photo(b'not an image')


def test_deletion_job_reaggregates_even_when_no_new_photo_is_pending(monkeypatch, tmp_path):
    from pipeline import run
    from pipeline.config import PipelineConfig
    conn = Connection()
    conn.commit = lambda: None
    loaded = []
    monkeypatch.setattr(run, 'fetch_pending_photos', lambda *args: [])
    monkeypatch.setattr(run, 'load_spot_results', lambda conn, spot: loaded.append(spot) or [])
    result = run.analyze(conn, LocalStorage(str(tmp_path)), PipelineConfig(), spot_id='removed-photo-spot')
    assert loaded == ['removed-photo-spot'] and result == []
    assert any("evidence='category'" in query and params == ('removed-photo-spot',) for query, params in conn.queries)
