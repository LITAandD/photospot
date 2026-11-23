"""Opt-in visitor examples. Raw uploads exist only during image processing.

These images never enter catalog_media, likes, or recommendation evidence.
PostgreSQL is the bounded pilot store. SQLite is allowed only for local tests.
No database creation or migration is performed by a web request.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import unicodedata
import warnings

from PIL import Image, ImageFilter, ImageOps
import psycopg
from psycopg.rows import dict_row
from psycopg.conninfo import conninfo_to_dict
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from uuid import UUID

VERSION = 'visitor-photo-v2-20261120'
MAX_FILE = 2 * 1024 * 1024
MAX_BODY = 3 * 1024 * 1024
MAX_PIXELS = 16_000_000
UTC = timezone.utc


def now():
    return datetime.now(UTC)


def stamp(value=None):
    return (value or now()).isoformat()


class Unavailable(Exception):
    pass


class Conflict(Exception):
    pass


class Capacity(Exception):
    pass


class InvalidImage(ValueError):
    """Only curated messages from image validation may reach the client."""


def unsafe_text(value):
    # Preserve legitimate joiners/emoji; reject control/surrogate and bidi overrides.
    return any(unicodedata.category(c) in {'Cc', 'Cs'} or c in '\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069' for c in value)


class Consent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: str
    rights: StrictBool
    location: StrictBool
    age14: StrictBool
    publication: StrictBool
    processing: StrictBool
    privacy: StrictBool
    overseas: StrictBool
    subject: str = Field(pattern='^(space|self)$')
    face_blur: StrictBool = False
    crop: StrictBool = False
    analysis: StrictBool = False

    @model_validator(mode='after')
    def check(self):
        if self.version != VERSION or not all((self.rights, self.location, self.age14, self.publication, self.processing, self.privacy, self.overseas)):
            raise ValueError('필수 동의를 확인해 주세요')
        if self.subject == 'self' and not self.face_blur:
            raise ValueError('본인 사진은 얼굴 블러 처리 동의가 필요해요')
        return self


class FaceBox(BaseModel):
    model_config = ConfigDict(extra='forbid')
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)
    width: float = Field(gt=0, le=1, allow_inf_nan=False)
    height: float = Field(gt=0, le=1, allow_inf_nan=False)

    @model_validator(mode='after')
    def bounds(self):
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError('얼굴 영역이 사진 밖에 있어요')
        return self


class Submission(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    token: str = Field(pattern='^[a-f0-9]{64}$')
    place_id: UUID
    credit: str = Field(min_length=1, max_length=40)
    caption: str = Field(default='', max_length=160)
    consent: Consent
    faces: list[FaceBox] = Field(default_factory=list, max_length=12)
    image: str = Field(min_length=10, max_length=MAX_FILE * 4 // 3 + 8)

    @model_validator(mode='after')
    def clean_text(self):
        self.credit = self.credit.strip()
        self.caption = self.caption.strip()
        if not self.credit or unsafe_text(self.credit + self.caption):
            raise ValueError('표시 이름과 설명을 확인해 주세요')
        if self.consent.subject == 'self' and not self.faces:
            raise ValueError('얼굴 전체를 가리는 영역을 지정해 주세요')
        if self.consent.subject == 'space' and self.faces:
            raise ValueError('사람이 있다면 본인 사진으로 선택해 주세요')
        return self


def policy():
    operator = os.environ.get('VISITOR_PHOTOS_OPERATOR', '').strip()
    contact = os.environ.get('VISITOR_PHOTOS_CONTACT', '').strip()
    url = os.environ.get('VISITOR_PHOTOS_POLICY_URL', '').strip()
    try:
        pending = int(os.environ.get('VISITOR_PHOTOS_PENDING_DAYS', '30'))
        published = int(os.environ.get('VISITOR_PHOTOS_PUBLIC_DAYS', '365'))
    except ValueError:
        # Invalid deployment settings must disable intake, never invent a retention period.
        pending = published = 0
    enabled = (os.environ.get('VISITOR_PHOTOS_ENABLED') == '1'
               and bool(operator and contact and url.startswith('https://'))
               and bool(os.environ.get('VISITOR_PHOTOS_DATABASE_URL') or local_db())
               and len(os.environ.get('VISITOR_PHOTOS_RATE_SECRET', '')) >= 32
               and 1 <= pending <= 90 and 1 <= published <= 730
               and (bool(local_db()) or len(os.environ.get('CRON_SECRET', '')) >= 32))
    return {'enabled': bool(enabled), 'version': VERSION, 'operator': operator, 'contact': contact,
            'policy_url': url, 'pending_days': pending, 'public_days': published, 'max_file_bytes': MAX_FILE}


def local_db():
    if os.environ.get('APP_ENV') == 'test' and not os.environ.get('VERCEL'):
        return os.environ.get('VISITOR_PHOTOS_TEST_SQLITE')
    return None


def required():
    if not policy()['enabled']:
        raise Unavailable('사진 접수를 준비하고 있어요')


class LocalConnection:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=()):
        return self.conn.execute(sql.replace('%s', '?'), params)


@contextmanager
def connection():
    test_path = local_db()
    if test_path:
        conn = sqlite3.connect(test_path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('BEGIN IMMEDIATE')
            yield LocalConnection(conn)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()
        return
    dsn = os.environ.get('VISITOR_PHOTOS_DATABASE_URL')
    if not dsn:
        raise Unavailable('사진 저장소가 준비되지 않았어요')
    options = {}
    if os.environ.get('VERCEL') and conninfo_to_dict(dsn).get('sslmode') not in {'require', 'verify-ca', 'verify-full'}:
        options['sslmode'] = 'require'
    with psycopg.connect(dsn, connect_timeout=3, row_factory=dict_row, **options) as conn:
        conn.execute("SET LOCAL statement_timeout = '5s'")
        yield conn  # context commits before caller returns a successful response


def migrate():
    with connection() as conn:
        for statement in Path(__file__).with_suffix('.sql').read_text(encoding='utf-8').split(';'):
            if statement.strip():
                conn.execute(statement)


def lock(conn):
    if not local_db():
        conn.execute("SELECT pg_advisory_xact_lock(721119, 1)")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def token_hash(token):
    return digest(token.encode())


def check_token(value):
    if not re.fullmatch('[a-f0-9]{64}', value):
        raise ValueError('접수 관리 코드를 확인해 주세요')
    return token_hash(value)


def prepare_image(raw: bytes, faces):
    """Decode before storage; no EXIF/ICC/comments/filename and no raw file on disk."""
    if len(raw) > MAX_FILE:
        raise InvalidImage('사진은 2MB까지 제출할 수 있어요')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw), formats=['JPEG', 'PNG', 'WEBP']) as source:
                if source.width * source.height > MAX_PIXELS:
                    raise InvalidImage('1600만 화소 이하의 사진을 선택해 주세요')
                if getattr(source, 'n_frames', 1) != 1:
                    if source.format != 'MPO':
                        raise InvalidImage('움직이는 사진은 받을 수 없어요. 정지 사진을 선택해 주세요')
                    source.seek(0)  # MPO auxiliary images are never decoded/stored.
                source.load()
                image = ImageOps.exif_transpose(source)
                if image.mode in {'RGBA', 'LA', 'PA'} or 'transparency' in image.info:
                    image = Image.alpha_composite(Image.new('RGBA', image.size, 'white'), image.convert('RGBA'))
                image = image.convert('RGB')
        if min(image.size) < 160:
            raise InvalidImage('사진의 짧은 변이 160px 이상이어야 해요')
        image.thumbnail((1600, 1600))
        for face in faces:
            x, y = int(face.x * image.width), int(face.y * image.height)
            right = min(image.width, round((face.x + face.width) * image.width))
            bottom = min(image.height, round((face.y + face.height) * image.height))
            if right - x < 16 or bottom - y < 16:
                raise InvalidImage('얼굴 영역이 너무 작아요. 머리 전체를 포함해 주세요')
            # Strong blur, not identity recognition. Human review is still mandatory.
            area = image.crop((x, y, right, bottom))
            area = area.filter(ImageFilter.GaussianBlur(radius=max(area.size) * 0.28))
            image.paste(area, (x, y))
        # Fresh pixels deliberately discard all decoder metadata.
        clean = Image.new('RGB', image.size)
        clean.paste(image)
        out = io.BytesIO()
        clean.save(out, format='JPEG', quality=85)
        data = out.getvalue()
        if len(data) > MAX_FILE:
            raise InvalidImage('처리된 사진이 너무 커요. 더 작은 사진을 선택해 주세요')
        return data, clean.width, clean.height
    except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise InvalidImage('JPEG·PNG·WebP 정지 사진을 확인해 주세요') from exc


def consume_limit(conn, ip):
    day = now().date().isoformat()
    key = hmac.new(os.environ['VISITOR_PHOTOS_RATE_SECRET'].encode(), (day + ':' + ip).encode(), hashlib.sha256).hexdigest()
    count = conn.execute('SELECT count(*) AS n FROM visitor_photos WHERE rate_key=%s', (key,)).fetchone()['n']
    total = conn.execute('SELECT count(*) AS n, COALESCE(sum(image_bytes),0) AS bytes FROM visitor_photos WHERE created_at>=%s', (day,)).fetchone()
    size = conn.execute('SELECT COALESCE(sum(image_bytes),0) AS bytes FROM visitor_photos').fetchone()['bytes']
    if count >= 5 or total['n'] >= 100 or size + MAX_FILE > 100 * 1024 * 1024:
        raise Capacity('접수 한도에 도달했어요. 잠시 후 다시 확인해 주세요')
    return key


def create(body, image, width, height, ip):
    required()
    sid, pid = str(body.id), str(body.place_id)
    receipt = token_hash(body.token)
    # Include consent/text/face selection in idempotency; a retry cannot alter permission.
    manifest = body.model_dump(mode='json', exclude={'image', 'token'})
    fingerprint = digest((json.dumps(manifest, sort_keys=True, ensure_ascii=False) + digest(image)).encode())
    with connection() as conn:
        lock(conn)
        old = conn.execute('SELECT token_hash,fingerprint,state FROM visitor_photos WHERE id=%s', (sid,)).fetchone()
        if old:
            if not hmac.compare_digest(old['token_hash'], receipt) or old['fingerprint'] != fingerprint:
                raise Conflict('동일 접수번호의 내용이 달라요. 새 접수로 제출해 주세요')
            return {'id': sid, 'state': old['state'], 'duplicate': True}
        rate_key = consume_limit(conn, ip)
        expiry = stamp(now() + timedelta(days=policy()['pending_days']))
        conn.execute('''INSERT INTO visitor_photos
            (id,place_id,token_hash,fingerprint,credit,caption,consent,policy_snapshot,faces,image,image_sha256,image_bytes,
             width,height,state,created_at,expires_at,rate_key)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s,%s)''',
            (sid, pid, receipt, fingerprint, body.credit, body.caption, json.dumps(body.consent.model_dump()),
             json.dumps(policy()), json.dumps([f.model_dump() for f in body.faces]), image, digest(image), len(image), width, height, stamp(), expiry, rate_key))
    return {'id': sid, 'state': 'pending', 'duplicate': False}


def owned(sid, token, image=False):
    hashed = check_token(token)
    with connection() as conn:
        fields = 'id,state,created_at,expires_at,place_id,credit,caption,note' + (',image' if image else '')
        row = conn.execute(f'SELECT {fields},token_hash FROM visitor_photos WHERE id=%s AND expires_at>%s', (sid, stamp())).fetchone()
        if not row or not hmac.compare_digest(row['token_hash'], hashed):
            return None
        return {k: row[k] for k in row.keys() if k != 'token_hash'}


def withdraw(sid, token):
    hashed = check_token(token)
    with connection() as conn:
        lock(conn)
        row = conn.execute('SELECT token_hash,state,policy_snapshot FROM visitor_photos WHERE id=%s', (sid,)).fetchone()
        if not row or not hmac.compare_digest(row['token_hash'], hashed):
            return False
        if row['state'] == 'withdrawn':
            return True  # retries must not extend retention indefinitely
        # Purge pixels, caption and credit in the same transaction that removes publication.
        conn.execute("""UPDATE visitor_photos SET state='withdrawn',image=NULL,image_bytes=0,credit='',caption='',
                     faces='[]',note='',reviewer='',expires_at=%s WHERE id=%s""",
                     (stamp(now() + timedelta(days=json.loads(row['policy_snapshot'])['pending_days'])), sid))
    return True


def public_items(pid):
    if not policy()['enabled']:
        return []
    with connection() as conn:
        rows = conn.execute("""SELECT id,credit,caption,created_at,consent FROM visitor_photos
            WHERE place_id=%s AND state='approved' AND expires_at>%s AND image IS NOT NULL
            ORDER BY created_at DESC,id LIMIT 12""", (pid, stamp())).fetchall()
    return [{'id': r['id'], 'credit': r['credit'], 'caption': r['caption'],
             'face_blurred': json.loads(r['consent'])['subject'] == 'self',
             'url': f"/preview/visitor-photos/images/{r['id']}"} for r in rows]


def public_image(sid):
    if not policy()['enabled']:
        return None
    with connection() as conn:
        row = conn.execute("""SELECT image,place_id FROM visitor_photos WHERE id=%s AND state='approved'
                           AND expires_at>%s AND image IS NOT NULL""", (sid, stamp())).fetchone()
    return row


def prune_expired(apply=False):
    """Idempotent retention cleanup; also runs while new submissions are paused."""
    with connection() as conn:
        lock(conn)
        cutoff = stamp()
        count = conn.execute('SELECT count(*) AS n FROM visitor_photos WHERE expires_at<=%s', (cutoff,)).fetchone()['n']
        if apply:
            conn.execute('DELETE FROM visitor_photos WHERE expires_at<=%s', (cutoff,))
            # UTC daily quotas never use previous days' pseudonymous keys.
            conn.execute("UPDATE visitor_photos SET rate_key='' WHERE rate_key<>'' AND created_at<%s", (now().date().isoformat(),))
    return count


def review(sid, sha, reviewer, decision, note, checks):
    if decision not in {'approve', 'reject'} or not reviewer.strip():
        raise ValueError('검수자와 결정을 확인해 주세요')
    with connection() as conn:
        lock(conn)
        row = conn.execute('SELECT * FROM visitor_photos WHERE id=%s', (sid,)).fetchone()
        if not row or row['state'] != 'pending' or row['expires_at'] <= stamp():
            raise Conflict('검수 대기 중인 유효한 접수만 처리할 수 있어요')
        if sha != row['image_sha256']:
            raise Conflict('검수한 파일과 저장된 사진이 달라요')
        if decision == 'approve':
            if not all(checks.get(k) is True for k in ('place', 'rights', 'faces', 'scene')):
                raise ValueError('지점·권리·얼굴 가림·촬영 예시 검수를 모두 확인해 주세요')
            Consent.model_validate(json.loads(row['consent']))
            # Active exact catalog ID remains mandatory at publication time.
            from .catalog_bridge import find
            from fastapi import HTTPException
            try:
                find(row['place_id'])
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
                raise Conflict('활성 카탈로그 장소가 아니에요') from exc
            conn.execute("""UPDATE visitor_photos SET state='approved',reviewer=%s,note=%s,
                         review_checks=%s,reviewed_at=%s,expires_at=%s WHERE id=%s""",
                         (reviewer.strip(), note, json.dumps(checks), stamp(),
                          stamp(now() + timedelta(days=json.loads(row['policy_snapshot'])['public_days'])), sid))
        else:
            conn.execute("""UPDATE visitor_photos SET state='rejected',image=NULL,image_bytes=0,credit='',caption='',faces='[]',
                         reviewer=%s,note=%s,reviewed_at=%s WHERE id=%s""", (reviewer.strip(), note, stamp(), sid))

