"""Explicit visitor-photo consent; no automatic reuse of private analysis uploads."""
import base64
import binascii
import json
import logging
import sqlite3
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from . import visitor_photos as store
from .catalog_bridge import find
from .rate_limit import client_ip, forwarded_scheme, per_minute, retry_after

router = APIRouter(prefix='/preview/visitor-photos', include_in_schema=False)
limits = [('/preview/visitor-photos', per_minute('RATE_LIMIT_VISITOR_PHOTOS_PER_MIN', 12))]
log = logging.getLogger(__name__)


def failure(exc):
    if isinstance(exc, store.Conflict):
        raise HTTPException(409, str(exc))
    if isinstance(exc, store.Capacity):
        raise HTTPException(429, str(exc), headers={'Retry-After': '3600'})
    # No SQL, DSN, photo body, management token or free text in logs/errors.
    log.warning('visitor_photo_store_failed type=%s', type(exc).__name__)
    raise HTTPException(503, '사진 접수 저장소에 연결하지 못했어요. 같은 접수번호로 다시 시도해 주세요')


STORE_ERRORS = (psycopg.Error, sqlite3.Error, store.Unavailable, store.Conflict, store.Capacity)


def guard(request, write=False):
    wait = retry_after(request, limits)
    if wait:
        raise HTTPException(429, '사진 요청이 너무 많아요. 잠시 후 다시 시도해 주세요', headers={'Retry-After': str(wait)})
    if write:
        own = forwarded_scheme(request) + '://' + request.url.netloc
        # Same-origin only; no session cookie or account credentials used.
        if request.headers.get('origin') != own or request.headers.get('sec-fetch-site') == 'cross-site':
            raise HTTPException(403, '포토스팟 화면에서만 접수할 수 있어요')
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            raise HTTPException(415, 'JSON 요청이 필요해요')


def bearer(request):
    value = request.headers.get('authorization', '')
    if not value.startswith('Bearer '):
        raise HTTPException(401, '접수 관리 코드가 필요해요')
    try:
        store.check_token(value[7:])
    except ValueError:
        raise HTTPException(401, '접수 관리 코드를 확인해 주세요')
    return value[7:]


@router.get('/policy')
def policy():
    return store.policy()


@router.post('', status_code=202)
async def submit(request: Request):
    guard(request, write=True)
    if not store.policy()['enabled']:
        raise HTTPException(503, '사진 접수를 준비하고 있어요')
    # Enforce size while streaming, including missing/forged Content-Length.
    parts, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > store.MAX_BODY:
            raise HTTPException(413, '사진은 2MB까지 제출할 수 있어요')
        parts.append(chunk)
    try:
        body = store.Submission.model_validate(json.loads(b''.join(parts)))
        raw = base64.b64decode(body.image, validate=True)
        if len(raw) > store.MAX_FILE:
            raise HTTPException(413, '사진은 2MB까지 제출할 수 있어요')
        await run_in_threadpool(find, str(body.place_id))
        image, width, height = await run_in_threadpool(store.prepare_image, raw, body.faces)
        del raw, parts
    except (ValidationError, ValueError, binascii.Error):
        raise HTTPException(422, '사진 파일·얼굴 영역·필수 동의를 확인해 주세요')
    try:
        return await run_in_threadpool(store.create, body, image, width, height, client_ip(request))
    except STORE_ERRORS as exc:
        failure(exc)


@router.get('/places/{place_id}')
def examples(place_id: UUID):
    find(str(place_id))
    try:
        return {'enabled': store.policy()['enabled'], 'items': store.public_items(str(place_id))}
    except STORE_ERRORS as exc:
        failure(exc)


@router.get('/images/{submission_id}')
def image(submission_id: UUID):
    try:
        row = store.public_image(str(submission_id))
    except STORE_ERRORS as exc:
        failure(exc)
    if not row:
        raise HTTPException(404, '공개된 예시사진을 찾을 수 없어요')
    find(row['place_id'])
    return Response(bytes(row['image']), media_type='image/jpeg',
                    headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


@router.get('/receipts/{submission_id}')
def status(submission_id: UUID, request: Request):
    guard(request)
    try:
        row = store.owned(str(submission_id), bearer(request))
    except STORE_ERRORS as exc:
        failure(exc)
    if not row:
        raise HTTPException(404, '접수 관리 코드가 다르거나 보관 기간이 지났어요')
    return row


@router.post('/receipts/{submission_id}/image')
def private_image(submission_id: UUID, request: Request):
    guard(request, write=True)
    try:
        row = store.owned(str(submission_id), bearer(request), image=True)
    except STORE_ERRORS as exc:
        failure(exc)
    if not row or not row.get('image'):
        raise HTTPException(404, '보관 중인 사진이 없어요')
    return Response(bytes(row['image']), media_type='image/jpeg', headers={'Cache-Control': 'no-store'})


@router.post('/receipts/{submission_id}/withdraw')
def withdraw(submission_id: UUID, request: Request):
    guard(request, write=True)
    try:
        found = store.withdraw(str(submission_id), bearer(request))
    except STORE_ERRORS as exc:
        failure(exc)
    if not found:
        raise HTTPException(404, '접수 관리 코드를 확인해 주세요')
    return {'state': 'withdrawn'}

