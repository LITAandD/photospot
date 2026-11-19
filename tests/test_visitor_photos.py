"""Visitor photo privacy/publication boundaries, on SQLite and PostgreSQL in CI."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import io
import json
import os
import shutil
import uuid

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from psycopg import sql
from psycopg.conninfo import make_conninfo
import psycopg
import pytest

from api import visitor_photos as store, visitor_photo_routes as routes
from api.preview import app
from api.rate_limit import SlidingWindow
from pipeline import place_catalog

PID = '3e425403-dffd-54ed-8d4c-eecb2223c763'
BASE = '/preview/visitor-photos'
HEADERS = {'Origin': 'http://testserver', 'Content-Type': 'application/json'}


@pytest.fixture(params=['sqlite', 'postgres'])
def setup(request, monkeypatch, tmp_path):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.delenv('VERCEL', raising=False)
    monkeypatch.setenv('VISITOR_PHOTOS_ENABLED', '1')
    monkeypatch.setenv('VISITOR_PHOTOS_OPERATOR', 'Test operator')
    monkeypatch.setenv('VISITOR_PHOTOS_CONTACT', 'test@example.test')
    monkeypatch.setenv('VISITOR_PHOTOS_POLICY_URL', 'https://example.test/policy')
    monkeypatch.setenv('VISITOR_PHOTOS_RATE_SECRET', 'test-rate-key-not-for-production-' * 2)
    monkeypatch.setattr(routes, 'limits', [(BASE, SlidingWindow(0))])
    source = place_catalog.ROOT / 'catalog' / 'places.sqlite3'
    catalog = tmp_path / 'catalog.sqlite3'
    shutil.copyfile(source, catalog)
    monkeypatch.setenv('PLACE_CATALOG_DB', str(catalog))
    schema = None
    if request.param == 'postgres':
        dsn = os.environ.get('DATABASE_URL')
        if not dsn:
            pytest.skip('PostgreSQL integration runs in CI; local test has no database service')
        schema = 'visitor_test_' + uuid.uuid4().hex
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        monkeypatch.delenv('VISITOR_PHOTOS_TEST_SQLITE', raising=False)
        monkeypatch.setenv('VISITOR_PHOTOS_DATABASE_URL', make_conninfo(dsn, options='-c search_path=' + schema))
    else:
        monkeypatch.setenv('VISITOR_PHOTOS_TEST_SQLITE', str(tmp_path / 'visitors.sqlite3'))
    store.migrate()
    yield TestClient(app)
    if schema:
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def photo():
    img = Image.new('RGB', (320, 240), 'white')
    draw = ImageDraw.Draw(img)
    for x in range(80, 240, 5):
        draw.line((x, 40, x, 160), fill='black', width=2)
    exif = Image.Exif()
    exif[271] = 'PRIVATE_CAMERA'
    exif[270] = 'PRIVATE_ADDRESS'
    buf = io.BytesIO()
    img.save(buf, format='JPEG', exif=exif.tobytes())
    return buf.getvalue()


def body():
    return {'id': str(uuid.uuid4()), 'token': 'ab' * 32, 'place_id': PID, 'credit': 'Test nickname', 'caption': 'Facade',
            'image': base64.b64encode(photo()).decode(), 'faces': [{'x': .25, 'y': 1 / 6, 'width': .5, 'height': .5}],
            'consent': {'version': store.VERSION, 'rights': True, 'location': True, 'age14': True, 'publication': True,
                        'processing': True, 'privacy': True, 'subject': 'self', 'face_blur': True, 'crop': False, 'analysis': False}}


def headers(b, token=None):
    return {**HEADERS, 'Authorization': 'Bearer ' + (token or b['token'])}


def approve(b, **overrides):
    with store.connection() as conn:
        row = conn.execute('SELECT image_sha256 FROM visitor_photos WHERE id=%s', (b['id'],)).fetchone()
    store.review(b['id'], overrides.get('sha', row['image_sha256']), 'operator-test', 'approve', '',
                 overrides.get('checks', dict(place=True, rights=True, faces=True, scene=True)))


def test_private_pending_then_review_then_withdraw(setup):
    c, b = setup, body()
    r = c.post(BASE, json=b, headers=HEADERS)
    assert r.status_code == 202, r.text
    assert r.json()['state'] == 'pending'
    assert c.get(BASE + '/images/' + b['id']).status_code == 404
    assert c.get(BASE + '/places/' + PID).json()['items'] == []
    own = c.get(BASE + '/receipts/' + b['id'], headers=headers(b))
    assert own.json()['state'] == 'pending'
    assert not {'token_hash', 'image', 'consent', 'rate_key'} & own.json().keys()
    assert c.get(BASE + '/receipts/' + b['id']).status_code == 401
    assert c.get(BASE + '/receipts/' + b['id'], headers=headers(b, 'cd' * 32)).status_code == 404
    clean = c.post(BASE + '/receipts/' + b['id'] + '/image', headers=headers(b), json={})
    assert clean.status_code == 200 and clean.headers['cache-control'] == 'no-store'
    image = Image.open(io.BytesIO(clean.content))
    assert not image.getexif()
    assert b'PRIVATE_CAMERA' not in clean.content and b'PRIVATE_ADDRESS' not in clean.content
    # Texture in the selected face area has been blurred, not just relabeled.
    raw = Image.open(io.BytesIO(photo()))
    assert image.crop((100, 60, 220, 140)).tobytes() != raw.crop((100, 60, 220, 140)).tobytes()
    with store.connection() as conn:
        saved = conn.execute('SELECT * FROM visitor_photos WHERE id=%s', (b['id'],)).fetchone()
        assert bytes(saved['image']) == clean.content != photo()
        assert json.loads(saved['consent'])['analysis'] is False
        assert saved['token_hash'] != b['token']
        assert json.loads(saved['policy_snapshot'])['operator'] == 'Test operator'
    approve(b)
    items = c.get(BASE + '/places/' + PID).json()['items']
    assert len(items) == 1 and items[0]['face_blurred'] is True
    public = c.get(BASE + items[0]['url'].removeprefix(BASE))
    assert public.status_code == 200 and public.content == clean.content
    assert public.headers['cache-control'] == 'no-store'
    assert c.post(BASE + '/receipts/' + b['id'] + '/withdraw', json={}, headers=headers(b)).status_code == 200
    assert c.get(BASE + '/images/' + b['id']).status_code == 404
    assert c.get(BASE + '/places/' + PID).json()['items'] == []
    with store.connection() as conn:
        row = conn.execute('SELECT * FROM visitor_photos WHERE id=%s', (b['id'],)).fetchone()
        assert row['image'] is None and row['credit'] == row['caption'] == ''
    with pytest.raises(store.Conflict):
        approve(b)


@pytest.mark.parametrize('kind', ['consent', 'face_consent', 'no_face', 'outside_face', 'wrong_place', 'fake_image', 'wrong_version'])
def test_reject_invalid_submission(setup, kind):
    b = body()
    if kind == 'consent': b['consent']['publication'] = False
    if kind == 'face_consent': b['consent']['face_blur'] = False
    if kind == 'no_face': b['faces'] = []
    if kind == 'outside_face': b['faces'][0]['width'] = 1
    if kind == 'wrong_place': b['place_id'] = str(uuid.uuid4())
    if kind == 'fake_image': b['image'] = base64.b64encode(b'not a photo, <script>bad</script>').decode()
    if kind == 'wrong_version': b['consent']['version'] = 'old'
    r = setup.post(BASE, json=b, headers=HEADERS)
    assert r.status_code == (404 if kind == 'wrong_place' else 422)
    assert 'PRIVATE_' not in r.text and b['token'] not in r.text
    with store.connection() as conn:
        assert conn.execute('SELECT count(*) AS n FROM visitor_photos').fetchone()['n'] == 0


def test_retries_idempotency_and_changed_consent(setup):
    b = body()
    first = setup.post(BASE, json=b, headers=HEADERS)
    assert first.status_code == 202
    retry = setup.post(BASE, json=b, headers=HEADERS)
    assert retry.json()['duplicate'] is True
    b['consent']['analysis'] = True
    assert setup.post(BASE, json=b, headers=HEADERS).status_code == 409
    b['consent']['analysis'] = False
    b['token'] = 'cd' * 32
    assert setup.post(BASE, json=b, headers=HEADERS).status_code == 409
    with store.connection() as conn:
        assert conn.execute('SELECT count(*) AS n FROM visitor_photos').fetchone()['n'] == 1


def test_parallel_duplicate_commits_once(setup):
    b = store.Submission.model_validate(body())
    image, width, height = store.prepare_image(photo(), b.faces)
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(lambda _: store.create(b, image, width, height, 'same-ip'), range(4)))
    assert sum(not x['duplicate'] for x in results) == 1


def test_operator_cannot_publish_without_reviews_or_matching_bytes(setup):
    b = body()
    assert setup.post(BASE, json=b, headers=HEADERS).status_code == 202
    with pytest.raises(ValueError):
        approve(b, checks={'place': True, 'rights': True, 'faces': False, 'scene': True})
    with pytest.raises(store.Conflict):
        approve(b, sha='bad')
    assert setup.get(BASE + '/places/' + PID).json()['items'] == []


def test_limits_cross_origin_disabled_expiry(setup, monkeypatch):
    b = body()
    assert setup.post(BASE, json=b, headers={**HEADERS, 'Origin': 'https://evil.test'}).status_code == 403
    assert setup.post(BASE, content=b'{}', headers={'Origin': 'http://testserver', 'Content-Type': 'text/plain'}).status_code == 415
    assert setup.post(BASE, content=b'x' * (store.MAX_BODY + 1), headers=HEADERS).status_code == 413
    monkeypatch.setenv('VISITOR_PHOTOS_ENABLED', '0')
    assert setup.post(BASE, json=b, headers=HEADERS).status_code == 503
    monkeypatch.setenv('VISITOR_PHOTOS_ENABLED', '1')
    assert setup.post(BASE, json=b, headers=HEADERS).status_code == 202
    approve(b)
    monkeypatch.setenv('VISITOR_PHOTOS_ENABLED', '0')
    assert setup.get(BASE + '/images/' + b['id']).status_code == 404
    # Pausing intake must never prevent withdrawal.
    assert setup.post(BASE + '/receipts/' + b['id'] + '/withdraw', json={}, headers=headers(b)).status_code == 200


def test_shared_quota_not_only_per_process(setup):
    for _ in range(5):
        assert setup.post(BASE, json=body(), headers=HEADERS).status_code == 202
    assert setup.post(BASE, json=body(), headers=HEADERS).status_code == 429


def test_reject_deletes_file_and_expired_approval_is_hidden(setup):
    b = body()
    assert setup.post(BASE, json=b, headers=HEADERS).status_code == 202
    with store.connection() as conn:
        sha = conn.execute('SELECT image_sha256 FROM visitor_photos WHERE id=%s', (b['id'],)).fetchone()['image_sha256']
    store.review(b['id'], sha, 'operator', 'reject', '얼굴을 더 넓게 가려 주세요', {})
    assert setup.post(BASE + '/receipts/' + b['id'] + '/image', json={}, headers=headers(b)).status_code == 404
    b = body()
    assert setup.post(BASE, json=b, headers=HEADERS).status_code == 202
    approve(b)
    with store.connection() as conn:
        conn.execute('UPDATE visitor_photos SET expires_at=%s WHERE id=%s', (store.stamp(store.now() - timedelta(days=1)), b['id']))
    assert setup.get(BASE + '/images/' + b['id']).status_code == 404
    assert setup.get(BASE + '/places/' + PID).json()['items'] == []


def test_failure_does_not_expose_upload_or_break_public_place(setup, monkeypatch):
    def fail(*args):
        raise psycopg.OperationalError('private connection information')
    monkeypatch.setattr(store, 'create', fail)
    r = setup.post(BASE, json=body(), headers=HEADERS)
    assert r.status_code == 503 and 'private connection' not in r.text
    assert setup.get('/preview/browse?city=seoul&visit_date=2026-11-23').status_code == 200


def test_orientation_and_animation():
    img = Image.new('RGB', (320, 240), 'red')
    exif = Image.Exif()
    exif[274] = 6
    data = io.BytesIO()
    img.save(data, 'JPEG', exif=exif)
    clean, width, height = store.prepare_image(data.getvalue(), [])
    assert (width, height) == (240, 320)
    assert not Image.open(io.BytesIO(clean)).getexif()
    animated = io.BytesIO()
    img.save(animated, 'PNG', save_all=True, append_images=[Image.new('RGB', img.size, 'blue')], duration=100)
    with pytest.raises(ValueError):
        store.prepare_image(animated.getvalue(), [])

