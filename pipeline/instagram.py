"""인스타그램 Graph API로 카페 사진을 '분석만' 하고 인기 신호를 기록한다.

두 경로
  1) 해시태그 검색: 카페 이름을 해시태그로 (#어니언성수). 비즈니스 계정 필요, 7일에 해시태그 30개 제한 → 인기 카페부터
  2) 비즈니스 디스커버리: 카페 공식 계정(places.instagram_handle)의 게시물. 시간당 200회

원칙 (플랫폼 약관)
  - 이미지는 저장하지 않는다. 메모리에서 색 통계·AI 판정만 뽑아 external_media 에 결과(숫자·라벨)만 남긴다
  - 게시물은 permalink 로만 참조하고, 앱에 보여줄 땐 공식 임베드(oEmbed)를 쓴다
  - 출시 전 Meta 플랫폼 약관·해시태그 API 정책을 법률 검토할 것 (분석 목적 처리 허용 범위)

인증: INSTAGRAM_ACCESS_TOKEN (장기 토큰), INSTAGRAM_USER_ID (우리 비즈니스 계정의 IG 사용자 ID)
"""
from __future__ import annotations

import io
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from PIL import Image
from psycopg.types.json import Jsonb

from .aggregate import PhotoResult, aggregate, analyze_photo
from .config import PipelineConfig
from .db import load_spot_results, upsert_scene

GRAPH = "https://graph.facebook.com/v21.0"
HASHTAG_BUDGET_PER_WEEK = 30
MEDIA_FIELDS = "id,media_type,media_url,permalink,timestamp,like_count,comments_count"


@dataclass
class Stats:
    places: int = 0
    media_seen: int = 0
    media_analyzed: int = 0
    scenes_updated: int = 0
    budget_skipped: int = 0
    errors: list[str] = field(default_factory=list)


def _default_http_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read())


def _default_http_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=20) as r:
        return r.read()


class InstagramClient:
    def __init__(self, access_token: str, ig_user_id: str, http_json=_default_http_json, http_bytes=_default_http_bytes):
        self.token, self.user_id, self._json, self._bytes = access_token, ig_user_id, http_json, http_bytes

    def _get(self, path: str, **params) -> dict:
        params["access_token"] = self.token
        return self._json(f"{GRAPH}/{path}?{urllib.parse.urlencode(params)}")

    def hashtag_id(self, tag: str) -> str | None:
        data = self._get("ig_hashtag_search", user_id=self.user_id, q=tag).get("data") or []
        return data[0]["id"] if data else None

    def hashtag_media(self, hashtag_id: str, kind: str = "top", limit: int = 50) -> list[dict]:
        return self._get(f"{hashtag_id}/{kind}_media", user_id=self.user_id, fields=MEDIA_FIELDS, limit=limit).get("data") or []

    def business_media(self, username: str, limit: int = 50) -> list[dict]:
        """공식 계정의 게시물 (비즈니스·크리에이터 계정만 조회 가능)."""
        fields = f"business_discovery.username({username}){{followers_count,media_count,media.limit({limit}){{{MEDIA_FIELDS}}}}}"
        bd = self._get(self.user_id, fields=fields).get("business_discovery") or {}
        return (bd.get("media") or {}).get("data") or []

    def image(self, url: str) -> bytes:
        return self._bytes(url)


def hashtag_for(name: str) -> str:
    """'어니언 성수' → '어니언성수'. 해시태그는 공백·특수문자를 못 쓴다."""
    return re.sub(r"[^0-9A-Za-z가-힣]", "", name)


def hashtags_used_this_week(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("""SELECT count(DISTINCT hashtag) FROM trend_signals
                        WHERE source = 'instagram_hashtag' AND collected_at > now() - interval '7 days'""")
        return cur.fetchone()[0]


def enrich_place(conn, client: InstagramClient, place_id: str, cfg: PipelineConfig, stats: Stats,
                 tagger=None, masker=None, max_media: int = 12, budget_left: int | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT name, instagram_handle FROM places WHERE id = %s", (place_id,))
        name, handle = cur.fetchone()
        cur.execute("SELECT id::text FROM spots WHERE place_id = %s ORDER BY created_at LIMIT 1", (place_id,))
        spot_id = cur.fetchone()[0]

    if handle:                                                          # 공식 계정이 있으면 그것을 우선 (해시태그 예산 절약)
        media, source, tag = client.business_media(handle), "instagram_account", handle
    else:
        if budget_left is not None and budget_left <= 0:
            stats.budget_skipped += 1
            return
        tag = hashtag_for(name)
        hid = client.hashtag_id(tag)
        if not hid:
            return
        media, source = client.hashtag_media(hid, "top"), "instagram_hashtag"
        recent = client.hashtag_media(hid, "recent")
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        n_recent = sum(1 for m in recent if _ts(m) and _ts(m) > cutoff)
        with conn.cursor() as cur:                                      # 인기 신호: 최근 30일 게시물 수(표본)
            cur.execute("INSERT INTO trend_signals (place_id, source, hashtag, recent_media_count) VALUES (%s, %s, %s, %s)",
                        (place_id, source, tag, n_recent))

    results: list[PhotoResult] = []
    for m in media:
        if m.get("media_type") not in ("IMAGE", "CAROUSEL_ALBUM") or not m.get("media_url"):
            continue
        stats.media_seen += 1
        with conn.cursor() as cur:
            cur.execute("SELECT labels FROM external_media WHERE source = 'instagram' AND media_id = %s", (m["id"],))
            cached = cur.fetchone()
        if cached:
            results.append(_from_labels(m["id"], spot_id, cached[0], source))
            continue
        if len(results) >= max_media:
            break
        try:
            img = Image.open(io.BytesIO(client.image(m["media_url"])))   # 메모리에서만 다룬다
            img.load()
            r = analyze_photo(m["id"], spot_id, "user_upload", img, cfg, masker, tagger)
        except Exception as e:
            stats.errors.append(f"{m['id']}: {e}")
            continue
        labels = {**r.labels_json(), "stats": r.stats.to_dict(), "time_slot": r.time_slot, "season": r.season,
                  "taken_at": m.get("timestamp"), "likes": m.get("like_count")}
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO external_media (place_id, spot_id, source, media_id, permalink, taken_at, labels, analyzed_at)
                           VALUES (%s, %s, 'instagram', %s, %s, %s, %s, now())
                           ON CONFLICT (source, media_id) DO UPDATE SET labels = EXCLUDED.labels, analyzed_at = now()""",
                        (place_id, spot_id, m["id"], m.get("permalink"), _ts(m), Jsonb(labels)))
        stats.media_analyzed += 1
        results.append(r)
    conn.commit()

    if results:                                                          # 우리 사진 + 인스타 분석 결과(방금 저장한 것 포함)를 합쳐 장면 확정
        for st in aggregate(load_spot_results(conn, spot_id), cfg):
            _, updated = upsert_scene(conn, st)
            stats.scenes_updated += int(updated)
        conn.commit()
    stats.places += 1


def _ts(m: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00"))
    except Exception:
        return None


def _from_labels(media_id: str, spot_id: str, lb: dict, source: str) -> PhotoResult:
    from .color import ColorStats
    return PhotoResult(media_id, spot_id, 0.7, lb["time_slot"], lb["time_source"], lb["season"], ColorStats(**lb["stats"]),
                       lb["color_tags"], tuple(lb["rule_lighting"]), set(lb["palette_elements"]), lb["vision"])


def enrich_cafes(conn, client: InstagramClient, cfg: PipelineConfig, limit: int = 30, tagger=None, masker=None, log=print) -> Stats:
    """사진이 없는 카페부터, 공식 계정이 있는 곳 우선, 그다음 해시태그 예산(7일 30개) 안에서."""
    stats = Stats()
    budget = HASHTAG_BUDGET_PER_WEEK - hashtags_used_this_week(conn)
    with conn.cursor() as cur:
        cur.execute("""SELECT p.id::text, p.instagram_handle IS NOT NULL AS has_handle FROM places p
                        WHERE p.category = 'cafe' AND p.status <> 'closed'
                          AND NOT EXISTS (SELECT 1 FROM external_media e WHERE e.place_id = p.id)
                          AND NOT EXISTS (SELECT 1 FROM photos ph JOIN spots s ON s.id = ph.spot_id WHERE s.place_id = p.id)
                        ORDER BY has_handle DESC, p.created_at LIMIT %s""", (limit,))
        rows = cur.fetchall()
    for place_id, has_handle in rows:
        try:
            enrich_place(conn, client, place_id, cfg, stats, tagger, masker, budget_left=None if has_handle else budget)
            if not has_handle:
                budget -= 1
        except Exception as e:
            conn.rollback()
            stats.errors.append(f"{place_id}: {e}")
    log(f"  카페 {stats.places}곳 · 게시물 {stats.media_analyzed}건 분석 · 장면 {stats.scenes_updated}개 갱신 · 예산 부족 {stats.budget_skipped}곳")
    return stats
