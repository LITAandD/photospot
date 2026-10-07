"""API 통합 테스트 (DATABASE_URL 필요, schema + 002 + 003 적용된 DB).

실행: DATABASE_URL=... python -m pytest tests/test_api.py -q
"""
import io
import os
import sys
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from PIL.TiffImagePlugin import IFDRational

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from api.config import Settings          # noqa: E402
from api.main import create_app           # noqa: E402

DSN = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="DATABASE_URL 없음")
USER_A = "a0000000-0000-0000-0000-000000000001"     # 시드: 여름쿨 라이트·웨이브·INFP·수 부족
GREENHOUSE_SPOT = "20000000-0000-0000-0000-000000000002"
SECRET = "test-secret"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    settings = Settings(database_url=DSN, jwt_secret=SECRET, storage_root=str(tmp_path_factory.mktemp("storage")), recommendation_backend='scenes')
    return TestClient(create_app(settings))


def auth(user_id=USER_A, role=None):
    import psycopg
    from api.tokens import issue_access
    with psycopg.connect(DSN) as conn:
        conn.execute("INSERT INTO users (id, is_admin) VALUES (%s,%s) ON CONFLICT (id) DO NOTHING", (user_id, role == "admin"))
    token, _ = issue_access(user_id, role == "admin", Settings(jwt_secret=SECRET))
    return {"Authorization": "Bearer " + token}


def jpeg_with_gps(taken="2026:10:10 15:20:00") -> bytes:
    img = Image.new("RGB", (640, 480), (200, 215, 235))
    exif = Image.Exif()
    exif.get_ifd(0x8769)[36867] = taken
    exif.get_ifd(0x8825)[2] = (IFDRational(37), IFDRational(34), IFDRational(0))          # GPS 위도 (지워져야 함)
    exif[271] = "TestPhone"                                        # 기기 제조사 (지워져야 함)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


# ---------------------------------------------------------------------------
def test_health_and_auth(client):
    assert client.get("/v1/health").json() == {"ok": True}
    r = client.get("/v1/me/profile")
    assert r.status_code == 401 and r.headers["content-type"].startswith("application/problem+json")
    assert client.get("/v1/me/profile", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_profile_roundtrip(client):
    uid = str(uuid.uuid4())
    r = client.put("/v1/me/profile", headers=auth(uid),
                   json={"gender": "male", "height_cm": 181, "pc_season": "winter_cool", "pc_subtone": "deep",
                         "body_type": "straight", "mbti": "ENTJ"})
    assert r.status_code == 200 and r.json()["height_band"] == "tall" and r.json()["saju_enabled"] is False
    assert client.put("/v1/me/profile", headers=auth(uid), json={"mbti": "XXXX"}).status_code == 422
    assert client.get("/v1/me/profile", headers=auth(uid)).json()["pc_season"] == "winter_cool"


def test_recommendations_for_user_a(client):
    r = client.get("/v1/recommendations", headers=auth(),
                   params={"lat": 37.5796, "lng": 126.9770, "radius_m": 5000, "date": "2026-10-10"})
    assert r.status_code == 200
    body = r.json()
    items = body["items"]
    assert items[0]["place_name"] == "창경궁 대온실" and items[0]["score"] == 78.3
    assert body["daily"] is None
    assert [(w['key'], w['weight']) for w in body['score_weights']] == [
        ('personal_color', 40), ('body_type', 30), ('height', 10), ('mbti', 12), ('element', 8), ('day_element', 4)]
    assert items[0]['scoring']['score'] == items[0]['score']
    assert items[0]["time_slot_label"] == "낮" and items[0]["distance_m"] > 0
    assert items[0]["reasons"][0]["label"] == "부드러운 자연광" and items[0]["reasons"][0]["points"] == 16
    assert all(i["recommendation_id"] for i in items)
    assert body["missing_inputs"] == []                                   # A는 모두 입력함
    # 월요일엔 휴궁인 장소가 빠진다
    mon = client.get("/v1/recommendations", headers=auth(),
                     params={"lat": 37.5796, "lng": 126.9770, "radius_m": 5000, "date": "2026-10-12"}).json()
    assert "창경궁 대온실" not in [i["place_name"] for i in mon["items"]]
    # 한국 밖 좌표는 거부
    assert client.get("/v1/recommendations", headers=auth(), params={"lat": 51.5, "lng": -0.1}).status_code == 422


def test_place_detail_and_feedback(client):
    rec = client.get("/v1/recommendations", headers=auth(),
                     params={"lat": 37.5796, "lng": 126.9770, "date": "2026-10-10"}).json()["items"][0]
    d = client.get(f"/v1/places/{rec['place_id']}", headers=auth(), params={"date": "2026-10-10"}).json()
    assert d["best_scene"]["score"] == 78.3 and d["open_on_visit_date"] is True
    assert d['best_scene']['scoring'] == rec['scoring']
    assert {t["kind"] for t in d["tips"]} == {"outfit", "composition", "light"}
    assert "월요일 휴무" in d["visit_notes"]
    closed = client.get(f"/v1/places/{rec['place_id']}", headers=auth(), params={"date": "2026-10-12"}).json()
    assert closed["open_on_visit_date"] is False and closed["best_scene"] is None

    fb = client.post(f"/v1/recommendations/{rec['recommendation_id']}/feedback", headers=auth(),
                     json={"visited": True, "rating": 5, "tag_corrections": {"lighting": "warm_artificial"}})
    assert fb.status_code == 201
    bad = client.post(f"/v1/recommendations/{rec['recommendation_id']}/feedback", headers=auth(),
                      json={"tag_corrections": {"lighting": "moonlight"}})
    assert bad.status_code == 422
    other = client.post(f"/v1/recommendations/{rec['recommendation_id']}/feedback",
                        headers=auth(str(uuid.uuid4())), json={"rating": 1})
    assert other.status_code == 404                                       # 남의 추천 기록엔 접근 불가


def test_place_group_filter_preserves_ranking_and_applies_before_limit(client):
    headers = auth()
    params = {'lat': 37.5796, 'lng': 126.9770, 'radius_m': 50000, 'date': '2026-10-10', 'limit': 50}
    baseline = client.get('/v1/recommendations', headers=headers, params=params).json()['items']
    assert baseline
    for group in ['cafe', 'travel', 'festival']:
        response = client.get('/v1/recommendations', headers=headers, params={**params, 'place_group': group, 'limit': 1})
        assert response.status_code == 200
        body = response.json()
        expected = [i['place_id'] for i in baseline if i['place_group'] == group][:1]
        assert body['place_group'] == group
        assert [i['place_id'] for i in body['items']] == expected
        assert all(i['place_group'] == group for i in body['items'])
    assert client.get('/v1/recommendations', headers=headers, params={**params, 'place_group': 'bad'}).status_code == 422


def test_saju_stores_only_percents(client):
    uid = str(uuid.uuid4())
    client.put("/v1/me/profile", headers=auth(uid), json={"pc_season": "summer_cool", "body_type": "wave"})
    assert client.put("/v1/me/saju", headers=auth(uid),
                      json={"birth_date": "1998-05-14", "consent": False}).status_code == 400
    r = client.put("/v1/me/saju", headers=auth(uid),
                   json={"birth_date": "1998-05-14", "birth_time": "14:30:00", "consent": True})
    assert r.status_code == 200
    body = r.json()
    assert body["method"] == "forceteller_v1" and body["has_birth_time"]
    assert body["pillars"]["day"]["hanja"] == "辛酉" and body["pillars"]["hour"]["hangul"] == "을미"
    assert body["dominant_element"] == "fire" and body["percents"]["fire"] == 45.0
    assert any("천간충" in c for c in body["corrections"])
    import psycopg
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='user_saju'")
        cols = {c[0] for c in cur.fetchall()}
        assert not any("birth" in c and c != "has_birth_time" for c in cols)   # 생년월일시 컬럼 자체가 없음
        assert "pillar" not in " ".join(cols)                                  # 네 기둥도 저장하지 않음
        cur.execute("SELECT dominant_element::text, fire FROM user_saju WHERE user_id=%s", (uid,))
        assert cur.fetchone() == ("fire", 45.0)
    card = client.get("/v1/me/type-card", headers=auth(uid)).json()
    assert card["name"] == "여름 쿨 웨이브"
    assert card["lucky"] is None  # initial result is profile-only
    # 음력 입력과 잘못된 음력 날짜
    ok = client.put("/v1/me/saju", headers=auth(uid),
                    json={"birth_date": "1998-03-18", "calendar": "lunar", "consent": True})
    assert ok.status_code == 200 and ok.json()["pillars"]["year"]["hanja"] == "戊寅"
    bad = client.put("/v1/me/saju", headers=auth(uid),
                     json={"birth_date": "1998-02-31", "calendar": "lunar", "consent": True})
    assert bad.status_code == 422
    assert client.delete("/v1/me/saju", headers=auth(uid)).status_code == 204
    assert client.get("/v1/me/type-card", headers=auth(uid)).json()["name"] == "여름 쿨 웨이브"


def test_saju_is_optional_per_search_and_daily_context_matches_detail(client):
    uid = str(uuid.uuid4())
    headers = auth(uid)
    profile = {"gender": "female", "height_cm": 168.5, "pc_season": "summer_cool",
               "pc_subtone": "light", "body_type": "wave", "mbti": "INFP"}
    assert client.put("/v1/me/profile", headers=headers, json=profile).status_code == 200
    saju = client.put("/v1/me/saju", headers=headers,
                      json={"birth_date": "1993-08-21", "birth_time": "09:30", "consent": True}).json()
    saved = client.get("/v1/me/profile", headers=headers).json()
    assert saved["height_cm"] == 168.5 and saved["saju_element"] == saju["dominant_element"]
    assert saved["saju_percents"] == saju["percents"]
    params = {"lat": 37.5796, "lng": 126.977, "date": "2026-10-10"}
    base = client.get("/v1/recommendations", headers=headers, params=params).json()
    assert base["daily"] is None
    # Compare the local preview formula with the real SQL for the same seeded scenes.
    from api.preview import evaluate_sample as evaluate, PreviewIn
    from datetime import date
    preview = evaluate(PreviewIn(profile=profile, visit_date=date(2026, 10, 10)))["recommendations"]
    assert {i["scene_id"]: i["score"] for i in base["items"]} == {i.scene_id: i.score for i in preview.items}
    params["use_saju"] = True
    added = client.get("/v1/recommendations", headers=headers, params=params).json()
    assert added["daily"]["personal_element"] == saju["dominant_element"]
    preview = evaluate(PreviewIn(profile=profile, visit_date=date(2026, 10, 10),
                                element=saju["dominant_element"], percents=saju["percents"], use_saju=True))["recommendations"]
    assert {i["scene_id"]: i["score"] for i in added["items"]} == {i.scene_id: i.score for i in preview.items}
    for item in added["items"]:
        detail = client.get(f"/v1/places/{item['place_id']}", headers=headers, params=params).json()
        assert detail["best_scene"]["score"] == item["score"]
        assert detail["best_scene"]["reasons"] == item["reasons"]
        assert detail["best_scene"]["recommended_elements"] == item["recommended_elements"]
    next_day = client.get("/v1/recommendations", headers=headers, params={**params, "date": "2026-10-13"}).json()
    assert added["daily"]["pillar"] != next_day["daily"]["pillar"]
    # Tied deficits must not multiply the element weight; balanced percentages remove that dimension.
    import psycopg
    for percents in [dict(wood=0, fire=30, earth=30, metal=0, water=40), dict.fromkeys(["wood", "fire", "earth", "metal", "water"], 20)]:
        with psycopg.connect(DSN) as conn:
            conn.execute("UPDATE user_saju SET wood=%s,fire=%s,earth=%s,metal=%s,water=%s WHERE user_id=%s",
                         (*[percents[k] for k in ["wood", "fire", "earth", "metal", "water"]], uid))
        actual = client.get("/v1/recommendations", headers=headers, params=params).json()
        expected = evaluate(PreviewIn(profile=profile, visit_date=date(2026, 10, 10), element=saju["dominant_element"],
                                      percents=percents, use_saju=True))["recommendations"]
        assert actual["daily"]["deficient_elements"] == expected.daily.deficient_elements
        assert {i["scene_id"]: i["score"] for i in actual["items"]} == {i.scene_id: i.score for i in expected.items}
    assert client.delete("/v1/me/saju", headers=headers).status_code == 204
    assert client.get("/v1/recommendations", headers=headers, params=params).json()["daily"] is None


def test_saju_unconfigured_returns_503(tmp_path):
    from api.services import UnconfiguredCalculator
    settings = Settings(database_url=DSN, jwt_secret=SECRET, storage_root=str(tmp_path))
    c = TestClient(create_app(settings, saju_calculator=UnconfiguredCalculator()))
    r = c.put("/v1/me/saju", headers=auth(str(uuid.uuid4())), json={"birth_date": "1998-05-14", "consent": True})
    assert r.status_code == 503


def test_diagnosis(client):
    qs = client.get("/v1/diagnosis/personal-color/questions").json()
    assert len(qs) == 6 and len(qs[0]["options"]) == 3
    r = client.post("/v1/diagnosis/personal-color", json={"answers": [1, 1, 1, 0, 0, 2]}).json()
    assert r["result"] == "summer_cool" and r["confidence"] == "high" and r["second"] == "winter_cool"
    b = client.post("/v1/diagnosis/body-type", json={"answers": [1, 1, 1, 0, 1]}).json()
    assert b["result"] == "wave" and b["confidence"] == "high"
    assert client.post("/v1/diagnosis/body-type", json={"answers": [1, 1]}).status_code == 422


def test_photo_upload_strips_metadata_and_queues_job(client):
    from api.worker import run_once
    from pipeline.config import PipelineConfig
    import psycopg
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:       # 이전 실행이 남긴 대기 작업 정리
        cur.execute("DELETE FROM jobs WHERE status='queued' AND payload->>'spot_id' = %s", (GREENHOUSE_SPOT,))
    uid = str(uuid.uuid4())
    files = {"file": ("me.jpg", jpeg_with_gps(), "image/jpeg")}
    r = client.post("/v1/photos", headers=auth(uid), data={"spot_id": GREENHOUSE_SPOT}, files=files)
    assert r.status_code == 403                                           # 동의 전
    client.post("/v1/me/consents", headers=auth(uid), json={"type": "photo_analysis"})
    r = client.post("/v1/photos", headers=auth(uid), data={"spot_id": GREENHOUSE_SPOT},
                    files={"file": ("me.jpg", jpeg_with_gps(), "image/jpeg")})
    assert r.status_code == 202 and r.json()["job_queued"] is True
    assert r.json()["taken_at"].startswith("2026-10-10T15:20")
    r2 = client.post("/v1/photos", headers=auth(uid), data={"spot_id": GREENHOUSE_SPOT},
                     files={"file": ("me2.jpg", jpeg_with_gps(), "image/jpeg")})
    assert r2.json()["job_queued"] is False                               # 같은 스팟 작업은 중복 없이 하나
    assert client.post("/v1/photos", headers=auth(uid), data={"spot_id": GREENHOUSE_SPOT},
                       files={"file": ("x.txt", b"hello", "text/plain")}).status_code == 415

    storage = client.app.state.storage
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("SELECT storage_path, taken_at FROM photos WHERE id = %s", (r.json()["photo_id"],))
        path, taken = cur.fetchone()
        saved = Image.open(storage.open_path(path))
        exif = saved.getexif()
        assert exif.get_ifd(0x8769).get(36867) == "2026:10:10 15:20:00"   # 촬영 시각은 유지
        assert not exif.get_ifd(0x8825) and 271 not in exif               # GPS·기기 정보는 삭제
        assert taken is not None
        # 작업 처리기가 큐를 소비해 장면을 만든다 (AI 판정 없이)
        job = run_once(conn, storage, PipelineConfig())
        assert job and job["kind"] == "analyze_spot"
        cur.execute("SELECT status FROM jobs WHERE id = %s", (job["id"],))
        assert cur.fetchone()[0] == "done"
        cur.execute("SELECT tag_source::text FROM scenes WHERE spot_id=%s AND time_slot='midday' AND season='all'",
                    (GREENHOUSE_SPOT,))
        assert cur.fetchone()[0] in ("manual", "verified")                # 사람이 확정한 태그는 보존

    # 탈퇴하면 올린 사진 파일까지 지워진다
    assert client.delete("/v1/me", headers=auth(uid)).status_code == 204
    assert not os.path.exists(storage.open_path(path))
    assert client.get("/v1/me/profile", headers=auth(uid)).status_code == 401


def test_admin_review_queue_and_verify(client):
    assert client.get("/v1/admin/review-queue", headers=auth()).status_code == 403
    import psycopg
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:           # 신뢰도 낮은 자동 장면을 직접 만든다
        cur.execute("""INSERT INTO spots (place_id, name) VALUES ('10000000-0000-0000-0000-000000000004', '검수 테스트 스팟')
                       RETURNING id::text""")
        spot_id = cur.fetchone()[0]
        cur.execute("""INSERT INTO scenes (spot_id, time_slot, season, lighting, tag_source, confidence, review_reasons)
                       VALUES (%s, 'morning', 'all', 'warm_artificial', 'auto', 0.01, ARRAY['사진 1장뿐']) RETURNING id::text""",
                    (spot_id,))
        target = cur.fetchone()[0]
    q = client.get("/v1/admin/review-queue", headers=auth(str(uuid.uuid4()), role="admin"), params={"limit": 200}).json()
    assert target in [i["scene_id"] for i in q]
    r = client.patch(f"/v1/admin/scenes/{target}", headers=auth(str(uuid.uuid4()), role="admin"),
                     json={"lighting": "diffused_natural", "elements": ["wood"], "verify": True})
    assert r.status_code == 204
    after = client.get("/v1/admin/review-queue", headers=auth(str(uuid.uuid4()), role="admin")).json()
    assert target not in [i["scene_id"] for i in after]                  # 검수 완료 → 대기열에서 빠짐


def test_empty_profile_can_browse_without_invented_scores(client):
    headers = auth(str(uuid.uuid4()))
    assert client.get('/v1/me/profile', headers=headers).json()['profile_exists'] is False
    client.put('/v1/me/profile', headers=headers, json={})
    result = client.get('/v1/recommendations', headers=headers,
                        params={'lat': 37.5796, 'lng': 126.977, 'date': '2026-10-10'}).json()
    assert result['items']
    assert all(r['score'] == 0 and r['reasons'] == [] for r in result['items'])
    assert all(r['spot_id'] != r['scene_id'] for r in result['items'])


def test_bookmarks_are_idempotent_and_account_scoped(client):
    headers, other = auth(str(uuid.uuid4())), auth(str(uuid.uuid4()))
    pid = '10000000-0000-0000-0000-000000000002'
    for _ in range(2): assert client.put(f'/v1/me/bookmarks/{pid}', headers=headers).status_code == 204
    assert len(client.get('/v1/me/bookmarks', headers=headers).json()) == 1
    assert client.get('/v1/me/bookmarks', headers=other).json() == []
    assert client.delete(f'/v1/me/bookmarks/{pid}', headers=headers).status_code == 204
    assert client.get('/v1/me/bookmarks', headers=headers).json() == []


def test_photo_feedback_cannot_reference_someone_elses_upload(client):
    owner, outsider = auth(str(uuid.uuid4())), auth(str(uuid.uuid4()))
    client.post('/v1/me/consents', headers=owner, json={'type': 'photo_analysis'})
    uploaded = client.post('/v1/photos', headers=owner, data={'spot_id': GREENHOUSE_SPOT},
                           files={'file': ('test.jpg', jpeg_with_gps(), 'image/jpeg')}).json()
    rec = client.get('/v1/recommendations', headers=outsider, params={
        'lat': 37.5796, 'lng': 126.977, 'date': '2026-10-10'}).json()['items'][0]
    result = client.post(f"/v1/recommendations/{rec['recommendation_id']}/feedback", headers=outsider,
                         json={'photo_id': uploaded['photo_id'], 'rating': 5})
    assert result.status_code == 404
    assert client.delete('/v1/me/consents/photo_analysis', headers=owner).status_code == 204
    import psycopg
    with psycopg.connect(DSN) as conn:
        assert conn.execute('SELECT 1 FROM photos WHERE id=%s', (uploaded['photo_id'],)).fetchone() is None
