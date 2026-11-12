"""POST /preview/events and /v1/events: optional usage events; 204 stored, 503 unavailable."""
import logging
from fastapi import APIRouter, HTTPException, Request, Response

from .analytics import EventIn, MAX_BODY_BYTES, store
from .rate_limit import per_minute, retry_after

preview_router = APIRouter()
router = APIRouter(prefix='/v1')
limits = [('/', per_minute('RATE_LIMIT_EVENTS_PER_MIN', 60))]


def record(request, body):
    if int(request.headers.get('content-length') or 0) > MAX_BODY_BYTES:
        raise HTTPException(413, '이벤트가 너무 커요')
    wait = retry_after(request, limits)
    if wait:
        raise HTTPException(429, '이벤트 요청이 너무 많아요', headers={'Retry-After': str(wait)})
    if not store(body.model_dump()):
        logging.getLogger(__name__).warning('analytics_event_not_stored')
        return Response(status_code=503, headers={'Retry-After': '60'})
    return Response(status_code=204)


@preview_router.post('/preview/events', status_code=204)
def preview_event(body: EventIn, request: Request):
    return record(request, body)


@router.post('/events', status_code=204, tags=['system'], summary='선택 동의 이용 이벤트 기록')
def account_event(body: EventIn, request: Request):
    """허용된 이름의 이벤트만 저장한다. 개인정보·계정 ID·IP는 기록하지 않으며 저장소가 없으면 503과 운영 로그로 알린다."""
    return record(request, body)
