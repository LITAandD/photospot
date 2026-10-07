"""네이버 카페 수집 · 인스타그램 보강 테스트 (가짜 응답, 실제 DB)."""
import io
import os
import sys
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pipeline.config import PipelineConfig                                          # noqa: E402
from pipeline.instagram import InstagramClient, Stats as IgStats, enrich_cafes, enrich_place, hashtag_for   # noqa: E402
from pipeline.naver_local import NaverLocalClient, clean_title, harvest, parse_coords   # noqa: E402

DSN = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="DATABASE_URL 없음")
CFG = PipelineConfig()
RUN = uuid.uuid4().hex[:6]           # 반복 실행해도 겹치지 않게


def naver_item(name, area, i, category="카페,디저트>카페"):
    return {"title": f"<b>{name}</b> {area}점", "category": category, "address": f"서울특별시 {area}구 어딘가 {i}",
            "roadAddress": f"서울특별시 {area}구 어느로 {i}", "mapx": str(int((126.95 + i * 0.001) * 1e7)), "mapy": str(int((37.55 + i * 0.001) * 1e7))}


def fake_naver(url, headers):
    assert headers["X-Naver-Client-Id"] == "id"
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["query"][0]
    area, theme = q.split()[0], q.split()[1] if len(q.split()) == 3 else ""
    items = [naver_item(f"{RUN}-{theme or '일반'}카페{i}", area, i) for i in range(4)]
    items.append(naver_item(f"{RUN}-분식집", area, 9, category="음식점>분식"))                 # 카페 아님
    return {"items": items}


def jpeg(color=(200, 215, 235)):
    buf = io.BytesIO(); Image.new("RGB", (320, 240), color).save(buf, format="JPEG"); return buf.getvalue()


# ---------------------------------------------------------------------------
def test_naver_parsing():
    assert clean_title("<b>어니언</b> 성수 &amp; 안국") == "어니언 성수 & 안국"
    assert parse_coords({"mapx": "1270584000", "mapy": "375447000"}) == (127.0584, 37.5447)
    assert parse_coords({"mapx": "abc", "mapy": "1"}) is None
    assert hashtag_for("어니언 성수 (Onion)") == "어니언성수Onion"


def test_harvest_cafes_with_theme_baselines():
    import psycopg
    client = NaverLocalClient("id", "secret", http_json=fake_naver)
    with psycopg.connect(DSN) as conn:
        st = harvest(conn, client, ["성수", "연남"], ["한옥", "화이트", ""], target=1000, log=lambda *_: None)
        assert st.queries == 6 and st.added == 24 and st.skipped_not_cafe == 6 and st.errors == []
        with conn.cursor() as cur:
            cur.execute("""SELECT p.category::text, s.color_temp::text, s.texture::text, s.confidence
                             FROM places p JOIN spots sp ON sp.place_id = p.id JOIN scenes s ON s.spot_id = sp.id
                            WHERE p.name = %s""", (f"{RUN}-한옥카페0 성수점",))
            assert cur.fetchone() == ("cafe", "warm", "rough", 0.25)          # 한옥 테마 → 웜톤·거친 질감
            cur.execute("SELECT s.color_temp::text, s.texture::text FROM places p JOIN spots sp ON sp.place_id = p.id JOIN scenes s ON s.spot_id = sp.id WHERE p.name = %s",
                        (f"{RUN}-화이트카페0 성수점",))
            assert cur.fetchone() == ("cool", "sleek")
            cur.execute("SELECT url FROM place_external_ids WHERE provider='naver' AND url LIKE %s LIMIT 1", ("%map.naver.com%",))
            assert cur.fetchone()
        again = harvest(conn, client, ["성수"], ["한옥"], target=1000, log=lambda *_: None)
        assert again.added == 0 and again.skipped_existing == 4                 # 이름+주소 기준 중복 제거


def test_instagram_enrichment_updates_scene_and_trend():
    import psycopg
    now = datetime.now(timezone.utc)
    media = [{"id": f"m{RUN}{i}", "media_type": "IMAGE", "media_url": f"https://cdn.example/{i}.jpg",
              "permalink": f"https://www.instagram.com/p/x{i}/", "timestamp": (now - timedelta(days=i * 3)).strftime("%Y-%m-%dT%H:%M:%S+0000"),
              "like_count": 100 - i} for i in range(6)]
    calls = []

    def fake_json(url):
        calls.append(url)
        if "ig_hashtag_search" in url:
            return {"data": [{"id": "hash1"}]}
        if "top_media" in url or "recent_media" in url:
            return {"data": media}
        if "business_discovery" in url:
            return {"business_discovery": {"followers_count": 1200, "media": {"data": media[:3]}}}
        raise AssertionError(url)

    client = InstagramClient("tok", "17841400000000000", http_json=fake_json, http_bytes=lambda url: jpeg())
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        # 사진 없는 카페 (네이버 수집처럼 초기 태그만 있음)
        cur.execute("""INSERT INTO places (name, category, sido, geom, status) VALUES (%s, 'cafe', '서울특별시', ST_MakePoint(127.05, 37.54)::geography, 'unverified') RETURNING id::text""", (f"{RUN} 인스타카페",))
        pid = cur.fetchone()[0]
        cur.execute("INSERT INTO spots (place_id, name) VALUES (%s, '대표 지점') RETURNING id::text", (pid,))
        sid = cur.fetchone()[0]
        cur.execute("""INSERT INTO scenes (spot_id, time_slot, season, color_temp, texture, tag_source, evidence, confidence)
                       VALUES (%s, 'midday', 'all', 'warm', 'rough', 'auto', 'category', 0.25)""", (sid,))
        conn.commit()

        st = IgStats()
        enrich_place(conn, client, pid, CFG, st, budget_left=5)
        assert st.media_analyzed == 6 and st.scenes_updated >= 1 and st.errors == []
        cur.execute("SELECT count(*), bool_and(permalink LIKE 'https://www.instagram.com/p/%%') FROM external_media WHERE place_id = %s", (pid,))
        assert cur.fetchone() == (6, True)                                     # 이미지 없이 결과만 저장
        cur.execute("SELECT recent_media_count, hashtag FROM trend_signals WHERE place_id = %s AND source='instagram_hashtag'", (pid,))
        assert cur.fetchone() == (6, hashtag_for(f"{RUN} 인스타카페"))
        cur.execute("SELECT color_temp::text, photo_count, evidence::text FROM scenes WHERE spot_id = %s AND time_slot='midday'", (sid,))
        color, n, evidence = cur.fetchone()
        assert color == "cool" and n == 6 and evidence == "photos"             # 파란 사진 6장 → 초기 '웜'이 '쿨'로, 근거는 사진
        cur.execute("SELECT scorable FROM scene_integrity WHERE scene_id = (SELECT id FROM scenes WHERE spot_id = %s AND time_slot='midday')", (sid,))
        assert cur.fetchone()[0] is True                                       # 사진 6장·신뢰도 충분 → 채점 대상

        # 공식 계정이 있으면 해시태그 대신 비즈니스 디스커버리, 예산을 쓰지 않음
        cur.execute("UPDATE places SET instagram_handle = 'cafe_official' WHERE id = %s", (pid,))
        cur.execute("DELETE FROM external_media WHERE place_id = %s", (pid,)); conn.commit()
        calls.clear()
        enrich_place(conn, client, pid, CFG, IgStats(), budget_left=0)
        assert any("business_discovery" in c for c in calls) and not any("ig_hashtag_search" in c for c in calls)

        # 해시태그 예산이 0이면 건너뛴다
        cur.execute("UPDATE places SET instagram_handle = NULL WHERE id = %s", (pid,)); conn.commit()
        st2 = IgStats(); enrich_place(conn, client, pid, CFG, st2, budget_left=0)
        assert st2.budget_skipped == 1


def test_enrich_cafes_respects_weekly_budget():
    import psycopg
    client = InstagramClient("tok", "1", http_json=lambda url: {"data": []}, http_bytes=lambda url: b"")
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO places (name, category, sido, geom, status) VALUES (%s, 'cafe', '서울특별시', ST_MakePoint(127.0, 37.5)::geography, 'unverified') RETURNING id::text""", (f"{RUN} 예산카페",))
        pid = cur.fetchone()[0]
        cur.execute("INSERT INTO spots (place_id, name) VALUES (%s, '대표 지점')", (pid,))
        for i in range(30):                                                       # 이번 주 이미 30개 사용
            cur.execute("INSERT INTO trend_signals (place_id, source, hashtag, recent_media_count) VALUES (%s, 'instagram_hashtag', %s, 0)", (pid, f"tag{RUN}{i}"))
        conn.commit()
        st = enrich_cafes(conn, client, CFG, limit=200, log=lambda *_: None)
        assert st.budget_skipped >= 1 and st.media_analyzed == 0
