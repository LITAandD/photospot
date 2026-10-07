"""TourAPI 지역 기반 목록(areaBasedList2)으로 장소를 일괄 수집한다.

  python -m pipeline.run import-tourapi-bulk --areas 1,6,39 --types 12,14 --target 500

한 항목마다: 장소 + 외부 ID + 대표 스팟 + 분류 코드 기반 초기 장면(신뢰도 0.3) + 대표 사진(공공누리 1·3유형만) + 분석 작업.
초기 장면 덕분에 가져온 즉시 추천에 나오고, 작업 처리기가 사진을 분석하면 자동 태그를 덮어쓴다.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass, field

from psycopg.types.json import Jsonb

from .category_tags import baseline_for, scenes_from
from .tourapi import BASE_URL, LICENSE_MAP, LocalStorage, _get, _http_json_default, fetch_detail_images, register_images

AREA_NAMES = {
    1: "서울특별시", 2: "인천광역시", 3: "대전광역시", 4: "대구광역시", 5: "광주광역시", 6: "부산광역시", 7: "울산광역시",
    8: "세종특별자치시", 31: "경기도", 32: "강원특별자치도", 33: "충청북도", 34: "충청남도", 35: "경상북도", 36: "경상남도",
    37: "전북특별자치도", 38: "전라남도", 39: "제주특별자치도",
}
CONTENT_TYPES = {12: "관광지", 14: "문화시설", 15: "축제공연행사", 28: "레포츠", 39: "음식점"}
KOREA_BBOX = (124.0, 33.0, 132.0, 39.0)     # 좌표 오류 필터


@dataclass
class Stats:
    fetched: int = 0
    added: int = 0
    skipped_existing: int = 0
    skipped_no_image_or_license: int = 0
    skipped_bad_coords: int = 0
    photos: int = 0
    detail_photos: int = 0
    jobs: int = 0
    errors: list[str] = field(default_factory=list)


def _sigungu(addr: str | None) -> str | None:
    if not addr:
        return None
    parts = addr.split()
    for p in parts[1:3]:
        if re.search(r"(구|군|시)$", p):
            return p
    return None


def iter_area(service_key: str, area: int, content_type: int, http_json=_http_json_default,
              page_size: int = 100, max_pages: int = 100, app_name: str = "PhotoSpot"):
    """지역 × 콘텐츠 유형의 목록을 페이지 단위로 넘긴다 (대표 이미지가 있는 항목만, 제목순)."""
    for page in range(1, max_pages + 1):
        params = {"serviceKey": service_key, "MobileOS": "ETC", "MobileApp": app_name, "_type": "json",
                  "numOfRows": page_size, "pageNo": page, "arrange": "O", "areaCode": area, "contentTypeId": content_type}
        raw = http_json(f"{BASE_URL}/areaBasedList2?{urllib.parse.urlencode(params)}")
        body = ((raw.get("response") or {}).get("body") or {})
        items = body.get("items") or {}
        items = items.get("item", []) if isinstance(items, dict) else []
        if isinstance(items, dict):
            items = [items]
        if not items:
            return
        yield from items
        if page * page_size >= int(body.get("totalCount") or 0):
            return


def import_items(conn, items, storage: LocalStorage | None, stats: Stats, http_get=_get,
                 download_images: bool = True, target: int | None = None, detail_images: bool = False,
                 service_key: str = "", http_json_bytes=_get, max_detail: int = 8) -> Stats:
    for it in items:
        if target is not None and stats.added >= target:
            break
        stats.fetched += 1
        try:
            added = _import_one(conn, it, storage, stats, http_get, download_images)
            conn.commit()
            if added and detail_images and storage is not None:
                # 상세 사진(보통 3~10장)까지 받아야 '사진 3장 이상' 채점 기준을 넘길 수 있다 (장소당 API 1회)
                cid, spot_id = added
                imgs = fetch_detail_images(service_key, cid, http_get=http_json_bytes)[:max_detail]
                stats.detail_photos += register_images(conn, spot_id, imgs, storage, http_get=http_get)
        except Exception as e:                       # 한 항목 실패가 전체를 멈추지 않게
            conn.rollback()
            stats.errors.append(f"{it.get('contentid')}: {e}")
    return stats


def _import_one(conn, it: dict, storage, stats: Stats, http_get, download_images: bool):
    cid = str(it.get("contentid") or "").strip()
    lic = LICENSE_MAP.get((it.get("cpyrhtDivCd") or "").strip())
    img = (it.get("firstimage") or "").strip()
    if not cid or not img or not lic:
        stats.skipped_no_image_or_license += 1
        return
    try:
        lng, lat = float(it.get("mapx")), float(it.get("mapy"))
    except (TypeError, ValueError):
        stats.skipped_bad_coords += 1
        return
    if not (KOREA_BBOX[0] <= lng <= KOREA_BBOX[2] and KOREA_BBOX[1] <= lat <= KOREA_BBOX[3]):
        stats.skipped_bad_coords += 1
        return

    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM place_external_ids WHERE provider = 'tourapi' AND external_id = %s", (cid,))
        if cur.fetchone():
            stats.skipped_existing += 1
            return
        b = baseline_for(it.get("cat1"), it.get("cat2"), it.get("cat3"), str(it.get("contenttypeid") or ""))
        sido = AREA_NAMES.get(int(it.get("areacode") or 0)) or (it.get("addr1") or "").split(" ")[0] or "미상"
        cur.execute("""INSERT INTO places (name, category, sido, sigungu, address, geom, status)
                       VALUES (%s, %s, %s, %s, %s, ST_MakePoint(%s, %s)::geography, 'unverified') RETURNING id::text""",
                    (it.get("title", "").strip(), b.category, sido, _sigungu(it.get("addr1")), it.get("addr1"), lng, lat))
        place_id = cur.fetchone()[0]
        cur.execute("""INSERT INTO place_external_ids (provider, external_id, place_id, url) VALUES ('tourapi', %s, %s, %s)""",
                    (cid, place_id, f"https://korean.visitkorea.or.kr/detail/ms_detail.do?cotid={cid}"))
        cur.execute("INSERT INTO spots (place_id, name, guide) VALUES (%s, '대표 지점', %s) RETURNING id::text",
                    (place_id, f"TourAPI 분류 {it.get('cat3') or it.get('cat2') or ''}"))
        spot_id = cur.fetchone()[0]

        for sc in scenes_from(b):                    # 분류 기반 초기 장면
            elements = sc.pop("elements")
            cols = ", ".join(sc.keys())
            cur.execute(f"""INSERT INTO scenes (spot_id, {cols}, tag_source, evidence, confidence, review_reasons)
                            VALUES (%s, {", ".join(["%s"] * len(sc))}, 'auto', 'category', 0.3, ARRAY['카테고리 기반 초기 태그 · 사진 분석 대기'])
                            ON CONFLICT (spot_id, time_slot, season) DO NOTHING RETURNING id::text""",
                        (spot_id, *sc.values()))
            row = cur.fetchone()
            if row:
                for e in elements:
                    cur.execute("INSERT INTO scene_elements (scene_id, element) VALUES (%s, %s) ON CONFLICT DO NOTHING", (row[0], e))

        if download_images and storage is not None:
            path = storage.save(f"tourapi/{cid}_first.jpg", http_get(img))
            cur.execute("""INSERT INTO photos (spot_id, source, source_ref, license, storage_path)
                           VALUES (%s, 'tourapi', %s, %s, %s)""", (spot_id, f"{cid}:first", lic, path))
            stats.photos += 1
            cur.execute("""INSERT INTO jobs (kind, payload) VALUES ('analyze_spot', %s)
                           ON CONFLICT (kind, (payload->>'spot_id')) WHERE status = 'queued' DO NOTHING RETURNING id""",
                        (Jsonb({"spot_id": spot_id}),))
            if cur.fetchone():
                stats.jobs += 1
    stats.added += 1
    return cid, spot_id


def bulk_import(conn, service_key: str, areas: list[int], types: list[int], storage: LocalStorage | None,
                target: int = 500, http_json=_http_json_default, http_get=_get, download_images: bool = True,
                log=print, detail_images: bool = False, http_json_bytes=_get, max_detail: int = 8) -> Stats:
    stats = Stats()
    for area in areas:
        for ct in types:
            if stats.added >= target:
                break
            before = stats.added
            import_items(conn, iter_area(service_key, area, ct, http_json), storage, stats, http_get, download_images, target,
                         detail_images, service_key, http_json_bytes, max_detail)
            log(f"  {AREA_NAMES.get(area, area)} · {CONTENT_TYPES.get(ct, ct)}: +{stats.added - before} (누적 {stats.added})")
    return stats


def summary(stats: Stats) -> str:
    return json.dumps({k: (v if k != "errors" else len(v)) for k, v in stats.__dict__.items()}, ensure_ascii=False)
