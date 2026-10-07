"""TourAPI(KorService2) 대량 수집기: 전국 장소를 사진과 함께 가져와 places/spots/photos에 등록하고 분석 작업을 큐에 넣는다.

  python -m pipeline.import_tourapi --target 500                       # 전국, 기본 유형, 사진 3장 이상
  python -m pipeline.import_tourapi --areas 1,39 --types 12,14 --target 200
  python -m pipeline.import_tourapi --keywords-only                    # 사진 명소 키워드 검색만

환경변수: DATABASE_URL, TOURAPI_KEY, STORAGE_ROOT
그 다음: python -m api.worker (또는 pipeline.run analyze) 로 태깅
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

import psycopg

from .tourapi import BASE_URL, LocalStorage, usable_images

AREAS = {1: "서울특별시", 2: "인천광역시", 3: "대전광역시", 4: "대구광역시", 5: "광주광역시", 6: "부산광역시",
         7: "울산광역시", 8: "세종특별자치시", 31: "경기도", 32: "강원특별자치도", 33: "충청북도", 34: "충청남도",
         35: "경상북도", 36: "경상남도", 37: "전북특별자치도", 38: "전라남도", 39: "제주특별자치도"}

# TourAPI 콘텐츠 유형 → 우리 카테고리. 39(음식점)는 카페 소분류(A05020900)만 받는다
CONTENT_TYPES = {12: "attraction", 14: "museum", 39: "cafe"}
CAFE_CAT3 = "A05020900"

# 사진 명소를 겨냥한 키워드 검색 (지역·유형 목록에서 놓치는 곳 보강)
PHOTO_KEYWORDS = ["온실", "식물원", "수목원", "정원", "미술관", "전망대", "한옥마을", "억새", "벚꽃", "해변", "등대",
                  "출렁다리", "스카이워크", "도서관", "성당", "저수지", "메타세쿼이아", "유채", "핑크뮬리", "카페거리",
                  "벽화마을", "야경", "호수공원", "생태공원", "폐선", "철길", "전통시장", "고택", "서원", "사찰"]

_WEEKDAYS = {"일": 0, "월": 1, "화": 2, "수": 3, "목": 4, "금": 5, "토": 6}


@dataclass
class Candidate:
    content_id: str
    name: str
    category: str
    sido: str
    sigungu: str | None
    address: str | None
    lat: float
    lng: float
    modified: str | None = None
    images: list[dict] = field(default_factory=list)
    rest_text: str | None = None
    rules: list[int] = field(default_factory=list)      # weekly_closed 요일
    notes: list[str] = field(default_factory=list)


class TourApi:
    """KorService2 호출. http_json을 바꿔 끼우면 테스트에서 가짜 응답을 쓸 수 있다."""

    def __init__(self, key: str, app_name: str = "PhotoSpot", http_json=None, pause: float = 0.15):
        self.key, self.app_name, self.pause = key, app_name, pause
        self._get = http_json or self._default_get
        self.calls = 0

    @staticmethod
    def _default_get(url: str, timeout: int = 20) -> dict:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())

    def call(self, op: str, **params) -> list[dict]:
        base = {"serviceKey": self.key, "MobileOS": "ETC", "MobileApp": self.app_name, "_type": "json"}
        url = f"{BASE_URL}/{op}?{urllib.parse.urlencode({**base, **{k: v for k, v in params.items() if v is not None}})}"
        self.calls += 1
        if self.pause:
            time.sleep(self.pause)                          # 일일 호출 한도·속도 제한 배려
        raw = self._get(url)
        items = ((raw.get("response") or {}).get("body") or {}).get("items") or {}
        items = items.get("item", []) if isinstance(items, dict) else []
        return [items] if isinstance(items, dict) else items

    def list_area(self, area: int, content_type: int, page: int, rows: int = 100) -> list[dict]:
        # arrange=Q: 수정일순, 대표 이미지가 있는 것만
        return self.call("areaBasedList2", areaCode=area, contentTypeId=content_type, numOfRows=rows, pageNo=page, arrange="Q",
                         cat3=CAFE_CAT3 if content_type == 39 else None)

    def search(self, keyword: str, page: int, rows: int = 100) -> list[dict]:
        return self.call("searchKeyword2", keyword=keyword, numOfRows=rows, pageNo=page, arrange="Q")

    def images(self, content_id: str) -> list[dict]:
        raw_items = self.call("detailImage2", contentId=content_id, numOfRows=50, pageNo=1)
        return usable_images({"response": {"body": {"items": {"item": raw_items}}}}, content_id)

    def intro(self, content_id: str, content_type: int) -> dict:
        items = self.call("detailIntro2", contentId=content_id, contentTypeId=content_type)
        return items[0] if items else {}


def parse_rest_days(text: str | None) -> tuple[list[int], str | None]:
    """'매주 월요일', '월·화요일 휴무', '연중무휴' 같은 문구 → 요일 목록. 해석 못 하면 메모."""
    if not text:
        return [], None
    t = re.sub(r"<[^>]+>|\s+", "", text)
    if "연중무휴" in t or "없음" in t:
        return [], None
    days = sorted({_WEEKDAYS[m] for m in re.findall(r"([일월화수목금토])(?=요일|,|·|/|\)|$)", t) if m in _WEEKDAYS})
    if days and not re.search(r"(둘째|셋째|첫째|넷째|마지막|공휴일|명절|설|추석|\d+주)", t):
        return days, None
    return [], f"쉬는 날 확인 필요: {text.strip()[:80]}"


def to_candidate(item: dict) -> Candidate | None:
    try:
        lat, lng = float(item["mapy"]), float(item["mapx"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (33 <= lat <= 39 and 124 <= lng <= 132):
        return None
    ctype = int(item.get("contenttypeid") or 0)
    category = CONTENT_TYPES.get(ctype)
    if category is None or (ctype == 39 and item.get("cat3") != CAFE_CAT3):
        return None
    area = int(item.get("areacode") or 0)
    addr = (item.get("addr1") or "").strip()
    return Candidate(str(item["contentid"]), (item.get("title") or "").strip(), category,
                     AREAS.get(area, addr.split(" ")[0] if addr else "미상"),
                     addr.split(" ")[1] if addr.count(" ") >= 1 else None, addr or None, lat, lng, item.get("modifiedtime"))


REST_FIELDS = {12: "restdate", 14: "restdateculture", 39: "restdatefood"}


class Importer:
    def __init__(self, api: TourApi, conn, storage: LocalStorage, min_photos: int = 3, download: bool = True, log=print):
        self.api, self.conn, self.storage, self.min_photos, self.download, self.log = api, conn, storage, min_photos, download, log
        self.seen: set[str] = set()
        self.stats = {"listed": 0, "skipped_dup": 0, "skipped_photos": 0, "imported": 0, "photos": 0}

    # --- 후보 수집 -------------------------------------------------------------
    def iter_candidates(self, areas: list[int], types: list[int], keywords: list[str]):
        for area in areas:
            for ctype in types:
                page = 1
                while True:
                    items = self.api.list_area(area, ctype, page)
                    if not items:
                        break
                    for it in items:
                        c = to_candidate(it)
                        if c:
                            yield c, ctype
                    if len(items) < 100:
                        break
                    page += 1
        for kw in keywords:
            page = 1
            while True:
                items = self.api.search(kw, page)
                if not items:
                    break
                for it in items:
                    c = to_candidate(it)
                    if c:
                        yield c, int(it.get("contenttypeid") or 12)
                if len(items) < 100:
                    break
                page += 1

    # --- DB ------------------------------------------------------------------
    def _exists(self, c: Candidate) -> bool:
        with self.conn.cursor() as cur:
            cur.execute("SELECT 1 FROM place_external_ids WHERE provider='tourapi' AND external_id=%s", (c.content_id,))
            if cur.fetchone():
                return True
            cur.execute("""SELECT 1 FROM places WHERE name = %s
                            AND ST_DWithin(geom, ST_MakePoint(%s, %s)::geography, 100)""", (c.name, c.lng, c.lat))
            return cur.fetchone() is not None

    def _insert(self, c: Candidate) -> str:
        with self.conn.cursor() as cur:
            cur.execute("""INSERT INTO places (name, category, sido, sigungu, address, geom, status, last_verified_at)
                           VALUES (%s, %s, %s, %s, %s, ST_MakePoint(%s, %s)::geography, 'unverified', now()) RETURNING id::text""",
                        (c.name, c.category, c.sido, c.sigungu, c.address, c.lng, c.lat))
            place_id = cur.fetchone()[0]
            cur.execute("""INSERT INTO place_external_ids (provider, external_id, place_id, url)
                           VALUES ('tourapi', %s, %s, NULL)""", (c.content_id, place_id))
            cur.execute("INSERT INTO spots (place_id, name) VALUES (%s, '대표 스팟') RETURNING id::text", (place_id,))
            spot_id = cur.fetchone()[0]
            for wd in c.rules:
                cur.execute("INSERT INTO operating_rules (place_id, rule_type, weekday, note) VALUES (%s, 'weekly_closed', %s, %s)",
                            (place_id, wd, c.rest_text))
            for img in c.images:
                path = f"tourapi/{c.content_id}_{img['source_ref'].split(':')[-1]}.jpg"
                if self.download:
                    data = self.api._default_get_bytes(img["url"]) if hasattr(self.api, "_default_get_bytes") else _get_bytes(img["url"])
                    path = self.storage.save(path, data)
                cur.execute("""INSERT INTO photos (spot_id, source, source_ref, license, storage_path)
                               VALUES (%s, 'tourapi', %s, %s, %s)""", (spot_id, img["source_ref"], img["license"], path))
            cur.execute("""INSERT INTO jobs (kind, payload) VALUES ('analyze_spot', %s)
                           ON CONFLICT (kind, (payload->>'spot_id')) WHERE status = 'queued' DO NOTHING""",
                        (psycopg.types.json.Jsonb({"spot_id": spot_id}),))
        self.conn.commit()
        return place_id

    # --- 실행 ------------------------------------------------------------------
    def run(self, areas: list[int], types: list[int], keywords: list[str], target: int) -> dict:
        for c, ctype in self.iter_candidates(areas, types, keywords):
            if self.stats["imported"] >= target:
                break
            self.stats["listed"] += 1
            if c.content_id in self.seen or self._exists(c):
                self.stats["skipped_dup"] += 1
                continue
            self.seen.add(c.content_id)
            c.images = self.api.images(c.content_id)
            if len(c.images) < self.min_photos:
                self.stats["skipped_photos"] += 1
                continue
            intro = self.api.intro(c.content_id, ctype)
            c.rest_text = intro.get(REST_FIELDS.get(ctype, "restdate"))
            c.rules, note = parse_rest_days(c.rest_text)
            if note:
                c.notes.append(note)
            self._insert(c)
            self.stats["imported"] += 1
            self.stats["photos"] += len(c.images)
            if self.stats["imported"] % 25 == 0:
                self.log(f"  {self.stats['imported']}곳 등록 (API 호출 {self.api.calls}회)")
        return self.stats


def _get_bytes(url: str, timeout: int = 20) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--areas", default="all", help="지역 코드 쉼표 구분, 기본 전국")
    ap.add_argument("--types", default="12,14,39", help="12 관광지, 14 문화시설, 39 카페")
    ap.add_argument("--keywords-only", action="store_true")
    ap.add_argument("--no-keywords", action="store_true")
    ap.add_argument("--min-photos", type=int, default=3)
    ap.add_argument("--target", type=int, default=500)
    ap.add_argument("--no-download", action="store_true", help="사진 파일은 받지 않고 경로만 기록 (테스트)")
    args = ap.parse_args()
    areas = list(AREAS) if args.areas == "all" else [int(a) for a in args.areas.split(",")]
    types = [] if args.keywords_only else [int(t) for t in args.types.split(",")]
    keywords = [] if args.no_keywords else PHOTO_KEYWORDS
    api = TourApi(os.environ["TOURAPI_KEY"])
    storage = LocalStorage(os.environ.get("STORAGE_ROOT", "./storage"))
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        stats = Importer(api, conn, storage, args.min_photos, download=not args.no_download).run(areas, types, keywords, args.target)
    print(json.dumps({**stats, "api_calls": api.calls}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
