"""네이버 지역 검색 API로 카페 목록을 모은다.

제약: 검색어 하나에 최대 5곳, 페이지 없음. 대신 하루 25,000회라 '동네 × 테마' 검색어를 많이 던져 모은다.
검색에 쓴 테마 키워드는 그 카페의 초기 태그가 된다 ("성수동 한옥 카페"로 나온 카페 → 웜톤·원목·직선).

  python -m pipeline.run harvest-naver-cafes --areas 성수동,연남동,을지로 --target 300

인증: NAVER_CLIENT_ID / NAVER_CLIENT_SECRET (네이버 개발자 센터 > 검색 API).
사진은 주지 않으므로, 이후 enrich-instagram 이나 사장님·사용자 사진으로 채운다.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from .category_tags import Baseline, GOLDEN_EXTRA, NIGHT_EXTRA, scenes_from

SEARCH_URL = "https://openapi.naver.com/v1/search/local.json"

# 테마 검색어 → 초기 장면 태그. 순서는 검색 우선순위 (앞쪽이 사진발과 더 관련 있음)
THEMES: dict[str, Baseline] = {
    "한옥": Baseline("cafe", color_temp="warm", brightness="mid", saturation="muted", lighting="diffused_natural", form="linear",
                    texture="rough", scale="medium", crowd_level="moderate", place_character="concept", elements=("wood", "earth")),
    "플라워": Baseline("cafe", color_temp="warm", brightness="bright_soft", saturation="mid", lighting="diffused_natural", form="curved",
                     texture="soft", scale="compact", place_character="concept", elements=("wood",)),
    "화이트": Baseline("cafe", color_temp="cool", brightness="bright_soft", saturation="muted", lighting="diffused_natural", form="linear",
                     texture="sleek", scale="medium", place_character="concept", photo_mood="structural", elements=("metal",)),
    "미니멀": Baseline("cafe", color_temp="neutral", brightness="bright_soft", saturation="muted", lighting="diffused_natural", form="linear",
                     texture="sleek", scale="medium", crowd_level="quiet", photo_mood="structural", elements=("metal",)),
    "빈티지": Baseline("cafe", color_temp="warm", brightness="mid", saturation="muted", lighting="warm_artificial", form="linear",
                     texture="rough", scale="compact", place_character="detail", elements=("wood", "earth")),
    "루프탑": Baseline("cafe", color_temp="neutral", brightness="bright_soft", saturation="mid", lighting="direct_golden", form="linear",
                     texture="sleek", scale="spacious", elements=("metal",), extra_scenes=GOLDEN_EXTRA + NIGHT_EXTRA),
    "오션뷰": Baseline("cafe", color_temp="cool", brightness="bright_soft", saturation="mid", lighting="diffused_natural", form="organic",
                     texture="sleek", scale="spacious", elements=("water",), extra_scenes=GOLDEN_EXTRA),
    "정원": Baseline("cafe", color_temp="neutral", brightness="bright_soft", saturation="mid", lighting="diffused_natural", form="organic",
                   texture="soft", scale="spacious", elements=("wood",)),
    "베이커리": Baseline("cafe", color_temp="warm", brightness="bright_soft", saturation="mid", lighting="diffused_natural", form="linear",
                      texture="rough", scale="spacious", crowd_level="busy", place_character="detail", elements=("earth", "wood")),
    "감성": Baseline("cafe", color_temp="warm", brightness="mid", saturation="muted", lighting="warm_artificial", form="curved",
                    texture="soft", scale="compact", place_character="concept", elements=("wood",)),
    "뷰": Baseline("cafe", color_temp="neutral", brightness="bright_soft", saturation="mid", lighting="diffused_natural", form="organic",
                  texture="sleek", scale="spacious", elements=("metal",), extra_scenes=GOLDEN_EXTRA),
    "": Baseline("cafe", color_temp="warm", brightness="mid", saturation="muted", lighting="warm_artificial", form="curved",
                 texture="soft", scale="compact", place_character="detail", elements=("wood",)),    # 테마 없는 일반 검색
}


@dataclass
class Stats:
    queries: int = 0
    fetched: int = 0
    added: int = 0
    skipped_existing: int = 0
    skipped_not_cafe: int = 0
    errors: list[str] = field(default_factory=list)


def _default_http(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


class NaverLocalClient:
    def __init__(self, client_id: str, client_secret: str, http_json=_default_http):
        self._headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
        self._get = http_json

    def search(self, query: str, sort: str = "comment") -> list[dict]:
        """최대 5건. sort=comment 는 리뷰 많은 순 (인기 카페가 먼저)."""
        url = f"{SEARCH_URL}?{urllib.parse.urlencode({'query': query, 'display': 5, 'start': 1, 'sort': sort})}"
        return (self._get(url, self._headers) or {}).get("items", [])


def clean_title(t: str) -> str:
    return re.sub(r"<[^>]+>", "", t or "").replace("&amp;", "&").strip()


def parse_coords(item: dict) -> tuple[float, float] | None:
    """mapx/mapy: WGS84 × 1e7 정수 문자열 (예: 1270584000, 375447000)."""
    try:
        x, y = int(item["mapx"]), int(item["mapy"])
    except (KeyError, ValueError, TypeError):
        return None
    lng, lat = x / 1e7, y / 1e7
    return (lng, lat) if 124 <= lng <= 132 and 33 <= lat <= 39 else None


def naver_key(name: str, road_address: str) -> str:
    """네이버 항목엔 장소 ID가 없어 이름+도로명주소로 중복을 판단한다."""
    return re.sub(r"\s+", "", f"{name}|{road_address}").lower()


def harvest(conn, client: NaverLocalClient, areas: list[str], themes: list[str] | None = None,
            target: int = 300, log=print) -> Stats:
    """동네 × 테마 검색어를 돌려 카페를 모은다. 이미 있는 카페는 건너뛴다."""
    themes = list(THEMES) if themes is None else themes
    stats = Stats()
    for theme in themes:                                   # 테마를 바깥 루프로: 사진발과 관련 있는 테마부터 전 지역
        for area in areas:
            if stats.added >= target:
                return stats
            query = f"{area} {theme} 카페".replace("  ", " ")
            try:
                items = client.search(query)
            except Exception as e:
                stats.errors.append(f"{query}: {e}")
                continue
            stats.queries += 1
            before = stats.added
            for it in items:
                _import_one(conn, it, theme, stats)
            conn.commit()
            log(f"  {query}: {len(items)}건 중 +{stats.added - before} (누적 {stats.added})")
    return stats


def _import_one(conn, it: dict, theme: str, stats: Stats) -> None:
    stats.fetched += 1
    name = clean_title(it.get("title"))
    if "카페" not in (it.get("category") or "") and "커피" not in (it.get("category") or ""):
        stats.skipped_not_cafe += 1
        return
    coords = parse_coords(it)
    road = (it.get("roadAddress") or it.get("address") or "").strip()
    if not name or not coords or not road:
        stats.skipped_not_cafe += 1
        return
    key = naver_key(name, road)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM place_external_ids WHERE provider = 'naver' AND external_id = %s", (key,))
        if cur.fetchone():
            stats.skipped_existing += 1
            return
        parts = road.split()
        sido, sigungu = (parts[0] if parts else "미상"), (parts[1] if len(parts) > 1 else None)
        cur.execute("""INSERT INTO places (name, category, sido, sigungu, address, geom, status)
                       VALUES (%s, 'cafe', %s, %s, %s, ST_MakePoint(%s, %s)::geography, 'unverified') RETURNING id::text""",
                    (name, sido, sigungu, road, coords[0], coords[1]))
        place_id = cur.fetchone()[0]
        cur.execute("INSERT INTO place_external_ids (provider, external_id, place_id, url) VALUES ('naver', %s, %s, %s)",
                    (key, place_id, "https://map.naver.com/p/search/" + urllib.parse.quote(name, safe="")))
        cur.execute("INSERT INTO spots (place_id, name, guide) VALUES (%s, '대표 지점', %s) RETURNING id::text",
                    (place_id, f"네이버 검색 테마: {theme or '일반'}"))
        spot_id = cur.fetchone()[0]
        for sc in scenes_from(THEMES.get(theme, THEMES[""])):
            elements = sc.pop("elements")
            cur.execute(f"""INSERT INTO scenes (spot_id, {", ".join(sc)}, tag_source, evidence, confidence, review_reasons)
                            VALUES (%s, {", ".join(["%s"] * len(sc))}, 'auto', 'category', 0.25,
                                    ARRAY['검색 테마 기반 초기 태그 · 사진 없음 (인스타/사장님 사진 대기)'])
                            ON CONFLICT (spot_id, time_slot, season) DO NOTHING RETURNING id::text""", (spot_id, *sc.values()))
            row = cur.fetchone()
            if row:
                for e in elements:
                    cur.execute("INSERT INTO scene_elements (scene_id, element) VALUES (%s, %s) ON CONFLICT DO NOTHING", (row[0], e))
    stats.added += 1
