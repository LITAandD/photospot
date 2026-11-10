"""Like routes for anonymous preview browsers and authenticated catalog users."""
import hashlib
import hmac
import os
import secrets
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel, Field, StrictBool

from . import photo_likes
from .catalog_media import photos_for
from .rate_limit import forwarded_scheme, per_day, per_minute, retry_after
from pipeline.photo_identity import photo_id

preview_router = APIRouter(prefix='/preview/photo-likes')
COOKIE = 'photospot_photo_voter'
limits = [('/preview/photo-likes', per_minute('RATE_LIMIT_PHOTO_LIKES_PER_MIN', 30))]
# Per address and day (per process): new anonymous voter cookies, then likes.
# Clearing cookies in a loop must not mint unlimited votes from one connection.
daily_limits = [('/preview/photo-likes/session', per_day('PHOTO_LIKES_NEW_VOTERS_PER_DAY', 30)),
                ('/preview/photo-likes/', per_day('PHOTO_LIKES_PER_DAY', 200))]


class LikeIn(BaseModel):
    photo_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    liked: StrictBool


class LikeOut(BaseModel):
    photo_id: str
    like_count: int
    liked: bool


def secret():
    value = os.environ.get('PHOTO_LIKES_COOKIE_SECRET', '')
    return value if len(value) >= 32 else ''


def browser_identity(request):
    token, _, signature = request.cookies.get(COOKIE, '').partition('.')
    key = secret()
    if not key or len(token) != 64 or any(c not in '0123456789abcdef' for c in token):
        return None
    expected = hmac.new(key.encode(), token.encode(), hashlib.sha256).hexdigest()
    return 'browser:' + token if hmac.compare_digest(expected, signature) else None


def allowed_origins(request):
    """This site as the browser sees it (the proxy's scheme) plus PHOTO_LIKES_ORIGINS."""
    own = forwarded_scheme(request) + '://' + request.url.netloc
    return {own, *(o.strip().rstrip('/') for o in os.environ.get('PHOTO_LIKES_ORIGINS', '').split(',') if o.strip())}


def check_browser_write(request):
    if not photo_likes.configured() or not secret():
        raise HTTPException(503, '좋아요 저장소 연결을 준비하고 있어요')
    # JSON-only writes plus exact Origin validation protect the anonymous cookie.
    origin = request.headers.get('origin')
    if origin and origin.rstrip('/') not in allowed_origins(request):
        raise HTTPException(403, '이 사이트에서만 좋아요를 보낼 수 있어요')
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, '이 사이트에서만 좋아요를 보낼 수 있어요')
    if request.headers.get('content-type', '').split(';')[0] != 'application/json':
        raise HTTPException(415, 'JSON 요청이 필요해요')
    wait = retry_after(request, limits)
    if wait:
        raise HTTPException(429, '좋아요 요청이 너무 많아요. 잠시 후 다시 시도해 주세요', headers={'Retry-After': str(wait)})


def daily_cap(request, rules):
    wait = retry_after(request, rules)
    if wait:
        raise HTTPException(429, '오늘 좋아요 참여 한도를 넘었어요. 내일 다시 시도해 주세요', headers={'Retry-After': str(wait)})


@preview_router.post('/session')
def session(request: Request, response: Response):
    check_browser_write(request)
    if not browser_identity(request):
        daily_cap(request, daily_limits[:1])
        token = secrets.token_hex(32)
        signature = hmac.new(secret().encode(), token.encode(), hashlib.sha256).hexdigest()
        response.set_cookie(COOKIE, token + '.' + signature, httponly=True, samesite='lax',
                            secure=os.environ.get('VERCEL') == '1' or forwarded_scheme(request) == 'https',
                            max_age=365 * 86400, path='/')
    return {'ok': True}


def change_like(place_id, body, identity, background: BackgroundTasks):
    from .catalog_bridge import find
    find(place_id)
    photo = next((p for p in photos_for([place_id]).get(place_id, []) if photo_id(p) == body.photo_id), None)
    if not photo:
        raise HTTPException(404, '추천에 사용할 수 있는 사진을 찾을 수 없어요')
    if not photo_likes.configured():
        raise HTTPException(503, '좋아요 저장소 연결을 준비하고 있어요')
    try:
        result = photo_likes.set_like(place_id, photo, identity, body.liked)
    except photo_likes.RevokedVoter:
        raise HTTPException(401, '탈퇴한 계정의 좋아요는 저장할 수 없어요') from None
    if body.liked:
        # The vote is committed; downloading and analysing the image happens after
        # the response so the heart never waits on an external photo host.
        background.add_task(photo_likes.analyze_later, place_id, photo)
    return result


@preview_router.post('/{place_id}', response_model=LikeOut)
def preview_like(place_id: UUID, body: LikeIn, request: Request, background: BackgroundTasks):
    check_browser_write(request)
    identity = browser_identity(request)
    if not identity:
        raise HTTPException(428, '좋아요를 저장하려면 브라우저 쿠키를 허용해 주세요')
    if body.liked:
        daily_cap(request, daily_limits[1:])
    return change_like(str(place_id), body, identity, background)
