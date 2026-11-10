"""POST /preview/events and /v1/events: fire-and-forget funnel events, always 204."""
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
    store(body.model_dump())
    return Response(status_code=204)


@preview_router.post('/preview/events', status_code=204)
def preview_event(body: EventIn, request: Request):
    return record(request, body)


@router.post('/events', status_code=204, tags=['system'], summary='익명 퍼널 이벤트 기록')
def account_event(body: EventIn, request: Request):
    """허용된 이름의 이벤트만 저장한다. 개인정보·계정 ID·IP는 기록하지 않으며 저장소가 없으면 버린다."""
    return record(request, body)
