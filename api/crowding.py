"""Detail-only public population observations and within-attraction forecasts."""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.client import HTTPException
from pathlib import Path
from threading import Lock
from time import monotonic
from urllib.error import URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, build_opener
from typing import Literal, TypedDict
from uuid import UUID

from fastapi import APIRouter, Response

from .catalog_bridge import find_many

router = APIRouter(prefix='/crowding')
KST = timezone(timedelta(hours=9))
FRESHNESS = timedelta(minutes=40)
LEVELS = ('여유', '보통', '약간 붐빔', '붐빔')
PLACES = {row['place_id']: row for row in json.loads(Path(__file__).with_name('crowd_places.json').read_text('utf-8'))}
AREAS = {row['area_code']: row['area_name'] for row in PLACES.values() if row['area_code']}
SAMPLE_AREA = 'POI009'


@dataclass(frozen=True)
class ForecastSite:
    catalog_name: str
    lat: float
    lng: float
    provider: tuple[str, str, str]  # areaCd, signguCd, tAtsNm


# Independently reviewed KTO crosswalk, including attractions outside Seoul.
FORECAST_SITES: dict[str, ForecastSite] = {}


class Sources(TypedDict):
    area: str | None
    forecast: bool


class AreaReading(TypedDict):
    area_name: str
    level: Literal['여유', '보통', '약간 붐빔', '붐빔']
    observed_at: str
    expires_at: str


class ForecastDay(TypedDict):
    date: str
    index: float


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_json(url):
    # Fixed provider URLs only. A key in a KTO query must never follow a redirect or enter logs.
    try:
        with build_opener(NoRedirect()).open(url, timeout=4) as response:
            body = response.read(200_001)
        if len(body) <= 200_000:
            payload = json.loads(body)
            if isinstance(payload, dict):
                return payload
    except (URLError, OSError, HTTPException, ValueError):
        pass
    return {}


def observation(payload, code, now):
    result = payload.get('RESULT')
    rows = payload.get('SeoulRtd.citydata_ppltn')
    if not isinstance(result, dict) or result.get('RESULT.CODE') != 'INFO-000':
        return None
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        return None
    row = rows[0]
    if (code not in AREAS or row.get('AREA_CD') != code or row.get('AREA_NM') != AREAS[code]
            or row.get('REPLACE_YN') != 'N' or row.get('AREA_CONGEST_LVL') not in LEVELS):
        return None
    try:
        observed = datetime.strptime(row['PPLTN_TIME'], '%Y-%m-%d %H:%M').replace(tzinfo=KST)
    except (TypeError, ValueError, KeyError):
        return None
    if not observed <= now < observed + FRESHNESS:
        return None
    return {'area_name': AREAS[code], 'level': row['AREA_CONGEST_LVL'], 'observed_at': observed.isoformat(),
            'expires_at': (observed + FRESHNESS).isoformat()}


def forecast_days(payload, site, today):
    response = payload.get('response')
    if not isinstance(response, dict):
        return []
    header, body = response.get('header'), response.get('body')
    if not isinstance(header, dict) or header.get('resultCode') not in ('0000', '00') or not isinstance(body, dict):
        return []
    items = body.get('items')
    rows = items.get('item') if isinstance(items, dict) else None
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        return []
    # A truncated provider page could hide a conflicting record for the same date.
    try:
        if int(body.get('totalCount', len(rows))) > len(rows):
            return []
    except (TypeError, ValueError):
        return []
    days = {}
    conflicts = set()
    for row in rows:
        if not isinstance(row, dict) or tuple(row.get(k) for k in ('areaCd', 'signguCd', 'tAtsNm')) != site:
            continue
        try:
            day = datetime.strptime(row['baseYmd'], '%Y%m%d').date()
            rate = float(row['cnctrRate'])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if not today <= day < today + timedelta(days=30) or not math.isfinite(rate) or not 0 <= rate <= 100:
            continue
        if day in days and days[day] != rate:
            conflicts.add(day)
        days[day] = rate
    return [{'date': d.isoformat(), 'index': days[d]} for d in sorted(days.keys() - conflicts)]


class SharedReads:
    """One in-flight provider read per allowlisted key, including during a cache miss."""
    def __init__(self):
        self.entries = {}
        self.locks = {}
        self.guard = Lock()

    def get(self, key, loader, ttl):
        with self.guard:
            lock = self.locks.setdefault(key, Lock())
        with lock:
            until, value = self.entries.get(key, (0, None))
            if monotonic() >= until:
                value = loader()
                until = monotonic() + (ttl if value else 30)
                self.entries[key] = until, value
            return value, max(0, int(until - monotonic()))


reads = SharedReads()


def sample_enabled(code):
    return code == SAMPLE_AREA and os.getenv('PHOTOSPOT_SEOUL_PUBLIC_SAMPLE') == '1'


@router.get('/places/{place_id}')
def place_sources(place_id: UUID) -> Sources:
    pid = str(place_id)
    reviewed, site = PLACES.get(pid), FORECAST_SITES.get(pid)
    sources = Sources(area=None, forecast=False)
    if not reviewed and not site:
        return sources
    place = find_many([pid]).get(pid)
    if place:
        identity = (place['name'], place['lat'], place['lng'])
        if reviewed and identity == (reviewed['name'], reviewed['lat'], reviewed['lng']):
            code = reviewed['area_code']
            sources['area'] = code if sample_enabled(code) else None
        if site and identity == (site.catalog_name, site.lat, site.lng):
            sources['forecast'] = bool(os.getenv('KTO_CONCENTRATION_SERVICE_KEY'))
    return sources


@router.get('/areas/{code}')
def area_observation(code: str, response: Response) -> AreaReading | None:
    if not sample_enabled(code):
        return None
    # This documented HTTP route is strictly anonymous. Private Seoul keys are unsupported
    # until TLS is verified on the actual API path. Do not accept a configurable key or URL here.
    url = 'http://openapi.seoul.go.kr:8088/sample/json/citydata_ppltn/1/5/' + quote(AREAS[code])
    payload, remaining = reads.get(('seoul', code), lambda: read_json(url), 300)
    now = datetime.now(KST)
    result = observation(payload, code, now)
    if result:
        seconds = int((datetime.fromisoformat(result['expires_at']) - now).total_seconds())
        # Canonical area URL shares the response across venues and Vercel instances.
        # Browser responses keep the application's existing no-store policy.
        response.headers['Vercel-CDN-Cache-Control'] = f'public, s-maxage={min(remaining, seconds)}'
    return result


@router.get('/places/{place_id}/forecast')
def visit_forecast(place_id: UUID) -> list[ForecastDay]:
    pid = str(place_id)
    site, key = FORECAST_SITES.get(pid), os.getenv('KTO_CONCENTRATION_SERVICE_KEY')
    if not site or not key or not place_sources(place_id)['forecast']:
        return []
    area, district, name = site.provider
    query = urlencode({'serviceKey': key, 'pageNo': 1, 'numOfRows': 100, 'MobileOS': 'ETC',
                       'MobileApp': 'PhotoSpot', '_type': 'json', 'areaCd': area, 'signguCd': district, 'tAtsNm': name})
    url = 'https://apis.data.go.kr/B551011/TatsCnctrRateService/tatsCnctrRatedList?' + query
    payload, _ = reads.get(('kto', pid), lambda: read_json(url), 300)
    return forecast_days(payload, site.provider, datetime.now(KST).date())
