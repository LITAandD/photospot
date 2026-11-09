"""Catalog photos as served to people: only images with a reusable licence by default.

Official brand/shop photos (e.g. '© Starbucks Korea') carry no reuse grant. They stay
in the catalog for provenance but are shown only when ALLOW_OFFICIAL_BRAND_PHOTOS=1,
which an operator may set only after obtaining written permission from the owner.

장소별 사진 목록은 프로필과 무관하므로 scoring_cache에 두고 요청 간 재사용한다(F005: 후보
수천 곳의 사진 3천여 장을 매 요청 정규식으로 다시 고르던 비용). thumb_url()은 목록 카드가 960px
썸네일 대신 받을 작은 위키미디어 썸네일 주소를 만든다(F034; 스키마에 thumb_url 필드가 생기면 커버에 싣는다).
"""
import os
import re
from urllib.parse import urlsplit, urlunsplit

from pipeline import catalog_photos
from pipeline.kogl_photos import LICENSE_URL as KOGL_TYPE_1
from .scoring_cache import store

REUSABLE_LICENSE_URLS = ('https://creativecommons.org/', 'https://www.gnu.org/licenses/')
THUMB_WIDTH = 320                       # 72px 카드·76px 갤러리 썸네일이 DPR 3까지 선명한 크기
_THUMB_NAME = re.compile(r'^(\d+)px-(.+)$')
_RASTER = re.compile(r'\.(?:jpe?g|png|gif)$', re.I)


def brand_photos_allowed() -> bool:
    return os.environ.get('ALLOW_OFFICIAL_BRAND_PHOTOS') == '1'


def reusable(photo: dict) -> bool:
    return ((photo.get('license_url') or '').startswith(REUSABLE_LICENSE_URLS)
            or photo.get('license_url') == KOGL_TYPE_1)


WIKIMEDIA_HOSTS = {'upload.wikimedia.org', 'thumb.wikimedia.org'}


def thumb_url(url, width=THUMB_WIDTH, original_width=None):
    """위키미디어 사진 URL의 width px 썸네일. 다른 호스트, 이미 더 작은 썸네일, 원본보다 큰 요청은 그대로 둔다.

    .../thumb/a/ab/File.jpg/960px-File.jpg?utm… → .../thumb/a/ab/File.jpg/320px-File.jpg?utm…
    .../commons/a/ab/File.jpg                   → .../commons/thumb/a/ab/File.jpg/320px-File.jpg
    카탈로그 URL의 utm 질의(커먼즈가 요청한 출처 표시)는 그대로 둔다.
    """
    try:
        parts = urlsplit(url or '')
    except ValueError:
        return url
    if parts.scheme != 'https' or parts.hostname not in WIKIMEDIA_HOSTS or parts.fragment:
        return url
    if original_width and width >= original_width:
        return url
    segments = parts.path.split('/')
    if 'thumb' in segments:
        match = _THUMB_NAME.match(segments[-1])
        if not match or int(match.group(1)) <= width:
            return url
        segments[-1] = f'{width}px-{match.group(2)}'
    else:
        # /wikipedia/commons/a/ab/File.jpg: 디렉터리 두 단계 + 파일명. 래스터 파일만 썸네일 경로가 같은 이름을 쓴다.
        if len(segments) < 6 or segments[2] != 'commons' or not _RASTER.search(segments[-1]):
            return url
        segments = segments[:3] + ['thumb'] + segments[3:] + [f'{width}px-{segments[-1]}']
    return urlunsplit(('https', parts.netloc, '/'.join(segments), parts.query, ''))


def cover_thumbnail(photo, width=THUMB_WIDTH):
    """커버 사진의 목록용 썸네일 주소. 원본 폭을 알면 그보다 크게 요청하지 않는다."""
    return thumb_url(photo['url'], width, photo.get('width'))


def photos_for(ids) -> dict[str, list[dict]]:
    ids = list(dict.fromkeys(ids))
    cache = store('photos')             # 장소 → 브랜드 사진까지 포함한 전체 목록, None이면 사진 없음
    missing = [pid for pid in ids if pid not in cache]
    if missing:
        fresh = catalog_photos.photos_for(missing)
        for pid in missing:
            cache[pid] = fresh.get(pid)
    allowed = brand_photos_allowed()
    result = {}
    for pid in ids:
        photos = cache.get(pid)
        if photos is None:
            continue
        if not allowed:
            photos = [p for p in photos if reusable(p)]
            if not photos:
                continue
        result[pid] = [dict(p) for p in photos]           # 호출부가 바꿔도 캐시는 그대로
    return result


def photo_counts_for(ids) -> dict[str, int]:
    if brand_photos_allowed():
        return catalog_photos.photo_counts_for(ids)
    ids, counts = list(ids), {}
    for start in range(0, len(ids), 400):   # Bounded SQLite parameter lists.
        counts.update({pid: len(photos) for pid, photos in photos_for(ids[start:start + 400]).items()})
    return counts
