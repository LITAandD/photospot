"""TourAPI 일괄 수집 테스트: 가짜 TourAPI 응답 620건 → 실제 DB → 즉시 추천 가능 확인."""
import io
import os
import random
import uuid
import sys
import urllib.parse

import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pipeline.category_tags import baseline_for, scenes_from        # noqa: E402
from pipeline.tourapi import LocalStorage                            # noqa: E402
from pipeline.tourapi_bulk import Stats, bulk_import, import_items, iter_area   # noqa: E402

DSN = os.environ.get("DATABASE_URL")
RUN = uuid.uuid4().hex[:5]
CAT3S = ["A01011200", "A02010800", "A02060500", "A02050100", "A02020700", "A05020900", "A01011700", "A02010100", "ZZZ"]
AREAS = {1: (37.55, 126.98), 6: (35.15, 129.05), 39: (33.40, 126.55)}


def fake_items(area: int, ct: int, n: int, seed: int):
    rng = random.Random(seed)
    lat0, lng0 = AREAS[area]
    for i in range(n):
        cat3 = CAT3S[i % len(CAT3S)]
        yield {"contentid": f"{RUN}{area}{ct}{i:05d}", "contenttypeid": str(ct), "title": f"테스트 장소 {RUN} {area}-{ct}-{i}",
               "addr1": f"{'서울특별시' if area == 1 else '부산광역시' if area == 6 else '제주특별자치도'} 어딘가구 어느길 {i}",
               "areacode": str(area), "mapx": f"{lng0 + rng.uniform(-0.3, 0.3):.6f}", "mapy": f"{lat0 + rng.uniform(-0.2, 0.2):.6f}",
               "firstimage": "" if i % 10 == 9 else f"http://tong.visitkorea.or.kr/{area}{ct}{i}.jpg",       # 10%는 사진 없음
               "cpyrhtDivCd": "Type2" if i % 7 == 6 else ("Type3" if i % 3 == 0 else "Type1"),              # 1/7은 상업 이용 금지
               "cat1": cat3[:3], "cat2": cat3[:5], "cat3": cat3}


def fake_http_json_factory(per_page_items):
    def get(url):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        area, ct, page, rows = int(q["areaCode"][0]), int(q["contentTypeId"][0]), int(q["pageNo"][0]), int(q["numOfRows"][0])
        all_items = per_page_items(area, ct)
        chunk = all_items[(page - 1) * rows: page * rows]
        return {"response": {"body": {"totalCount": len(all_items), "items": {"item": chunk} if chunk else ""}}}
    return get


JPEG = io.BytesIO(); Image.new("RGB", (64, 48), (200, 180, 160)).save(JPEG, format="JPEG")
fake_get = lambda url: JPEG.getvalue()


# ---------------------------------------------------------------------------
def test_baseline_mapping_specificity():
    beach = baseline_for("A01", "A0101", "A01011200", "12")
    assert beach.color_temp == "cool" and "water" in beach.elements and len(scenes_from(beach)) == 2   # 낮 + 골든아워
    cafe = baseline_for("A05", "A0502", "A05020900", "39")
    assert cafe.category == "cafe" and cafe.lighting == "warm_artificial"
    fallback = baseline_for(None, None, None, "14")
    assert fallback.category == "museum" and scenes_from(fallback)[0]["lighting"] == "diffused_natural"
    unknown_cat3 = baseline_for("A02", "A0206", "A02069999", "14")
    assert unknown_cat3.category == "museum"                                # cat2 규칙으로 내려감


def test_iter_area_paginates():
    items = list(iter_area("k", 1, 12, fake_http_json_factory(lambda a, c: list(fake_items(a, c, 250, 1))), page_size=100))
    assert len(items) == 250


@pytest.mark.skipif(not DSN, reason="DATABASE_URL 없음")
def test_bulk_import_600_places(tmp_path):
    import psycopg
    per_area = {1: 340, 6: 260, 39: 200}           # 800건 → 사진 없음·라이선스 제외 후 약 620건
    http_json = fake_http_json_factory(lambda a, c: list(fake_items(a, c, per_area[a], a)) if c == 12 else [])
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM places")
            before = cur.fetchone()[0]
        stats = bulk_import(conn, "key", [1, 6, 39], [12], LocalStorage(str(tmp_path)), target=10_000,
                            http_json=http_json, http_get=fake_get, log=lambda *_: None)
        assert stats.errors == []
        assert stats.added >= 500 and stats.skipped_no_image_or_license > 0
        assert stats.photos == stats.added and stats.jobs == stats.added
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM places")
            assert cur.fetchone()[0] == before + stats.added
            # 모든 새 장소에 초기 장면이 있다
            cur.execute("""SELECT count(*) FROM places p WHERE p.name LIKE %s
                              AND NOT EXISTS (SELECT 1 FROM spots s JOIN scenes sc ON sc.spot_id = s.id WHERE s.place_id = p.id)""", (f"테스트 장소 {RUN} %",))
            assert cur.fetchone()[0] == 0
            # 분류 기반 초기 태그는 '분석 대기'일 뿐 채점되지 않는다 (사진 근거가 생기기 전까지 추천에 나오지 않음)
            cur.execute("""SELECT count(*) FILTER (WHERE evidence = 'category'), count(*) FILTER (WHERE scorable)
                             FROM scene_integrity WHERE place_name LIKE %s""", (f"테스트 장소 {RUN} %",))
            category_scenes, scorable = cur.fetchone()
            assert category_scenes >= stats.added and scorable == 0
            cur.execute("SELECT count(*) FROM recommend_places_near('a0000000-0000-0000-0000-000000000001', '2026-10-10', 35.15, 129.05, 30000, 50) r JOIN places p ON p.id = r.place_id WHERE p.name LIKE %s", (f"테스트 장소 {RUN} %",))
            assert cur.fetchone()[0] == 0
            cur.execute("SELECT count(*) FROM scene_review_queue q JOIN scenes s ON s.id = q.scene_id JOIN spots sp ON sp.id = s.spot_id JOIN places p ON p.id = sp.place_id WHERE p.name LIKE %s", (f"테스트 장소 {RUN} %",))
            assert cur.fetchone()[0] >= stats.added                        # 초기 태그는 모두 검수 대기열에
        # 다시 돌리면 중복 없이 전부 건너뛴다
        again = bulk_import(conn, "key", [1], [12], LocalStorage(str(tmp_path)), target=10_000,
                            http_json=http_json, http_get=fake_get, log=lambda *_: None)
        assert again.added == 0 and again.skipped_existing > 0


@pytest.mark.skipif(not DSN, reason="DATABASE_URL 없음")
def test_import_rejects_bad_coordinates_and_stops_at_target(tmp_path):
    import psycopg
    items = list(fake_items(39, 14, 30, 9))
    items[0]["mapx"], items[0]["mapy"] = "0", "0"
    items[1]["mapx"] = "abc"
    with psycopg.connect(DSN) as conn:
        stats = import_items(conn, items, LocalStorage(str(tmp_path)), Stats(), http_get=fake_get, target=5)
        assert stats.added == 5 and stats.skipped_bad_coords == 2
