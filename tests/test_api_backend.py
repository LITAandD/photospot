"""Catalog-mode feedback, cross-backend bookmarks, transactions and pooled connections (DATABASE_URL 필요)."""
import os
import uuid
from datetime import datetime, timezone

import psycopg
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.auth import CurrentUser, current_user
from api.config import Settings
from api.db import DB
from api.main import create_app
from api.providers import Identity
from api.tokens import issue_access
from pipeline import catalog_photos as photos, place_catalog as catalog

DSN = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="DATABASE_URL 없음")
SECRET = "backend-test-secret-at-least-32-bytes"
SEED_PLACE = "10000000-0000-0000-0000-000000000002"           # 창경궁 대온실 (scenes backend)


def auth(user_id):
    with psycopg.connect(DSN) as conn:
        conn.execute("INSERT INTO users (id) VALUES (%s) ON CONFLICT (id) DO NOTHING", (user_id,))
    return {"Authorization": "Bearer " + issue_access(user_id, False, Settings(jwt_secret=SECRET))[0]}


def app_for(backend, tmp_path, **kwargs):
    return create_app(Settings(database_url=DSN, jwt_secret=SECRET, storage_root=str(tmp_path),
                               recommendation_backend=backend, **kwargs))


@pytest.fixture
def catalog_db(tmp_path, monkeypatch):
    path = tmp_path / "public.sqlite3"
    monkeypatch.setenv("PLACE_CATALOG_DB", str(path))
    catalog.import_response("seoul", {"elements": [
        {"type": "node", "id": n, "lat": 37.5796 + n / 10000, "lon": 126.977, "tags": {"name": f"Cafe {n}", "amenity": "cafe"}}
        for n in (1, 2, 3)]})
    from tests.test_catalog_photos import image_page
    rows = sorted(catalog.search(37.5796, 126.977, 2000), key=lambda r: r["osm_id"])
    photos.store_photos([{**photos.reusable_image(image_page()), "place_id": rows[0]["id"],
                          "match_method": "reviewed:branch", "match_ref": "test", "priority": 1}], path)
    return rows


def checked_out(app):
    stats = app.state.pool.get_stats()
    return stats["pool_size"] - stats["pool_available"]


# --- 1. 카탈로그 추천 피드백 ------------------------------------------------------
def test_catalog_recommendation_feedback_is_stored_per_user_and_place(catalog_db, tmp_path):
    uid = str(uuid.uuid4())
    headers = auth(uid)
    with TestClient(app_for("catalog", tmp_path)) as client:
        items = client.get("/v1/recommendations", headers=headers,
                           params={"lat": 37.5796, "lng": 126.977, "date": "2026-10-10"}).json()["items"]
        item = items[0]
        url = f"/v1/recommendations/{item['recommendation_id']}/feedback"
        assert client.post(url, headers=headers, json={"visited": True, "rating": 4}).status_code == 201
        assert client.post(url, headers=headers, json={"rating": 5, "tag_corrections": {"lighting": "warm_artificial"}}).status_code == 201
        assert client.post(url, headers=headers, json={"tag_corrections": {"lighting": "moonlight"}}).status_code == 422
        assert client.post(url, headers=headers, json={"photo_id": str(uuid.uuid4())}).status_code == 404
        assert client.post("/v1/recommendations/987654321/feedback", headers=headers, json={"rating": 1}).status_code == 404
        other = str(uuid.uuid4())
        assert client.post(url, headers=auth(other), json={"rating": 2}).status_code == 201
        with psycopg.connect(DSN) as conn:
            rows = conn.execute("SELECT user_id::text, place_id::text, visited, rating, tag_corrections FROM catalog_feedback "
                                "WHERE user_id = ANY(%s::uuid[]) ORDER BY rating", ([uid, other],)).fetchall()
        assert rows == [(other, item["place_id"], None, 2, None),
                        (uid, item["place_id"], None, 5, {"lighting": "warm_artificial"})]
        assert client.delete("/v1/me", headers=headers).status_code == 204
        with psycopg.connect(DSN) as conn:
            assert conn.execute("SELECT count(*) FROM catalog_feedback WHERE user_id=%s", (uid,)).fetchone()[0] == 0


# --- 9. 추천 방식이 바뀌어도 저장한 장소 유지 ----------------------------------------
def test_bookmarks_survive_switching_recommendation_backend(catalog_db, tmp_path):
    uid = str(uuid.uuid4())
    headers = auth(uid)
    cafe = catalog_db[0]["id"]
    with TestClient(app_for("scenes", tmp_path)) as scenes, TestClient(app_for("catalog", tmp_path)) as cat:
        assert scenes.put(f"/v1/me/bookmarks/{SEED_PLACE}", headers=headers).status_code == 204
        assert cat.put(f"/v1/me/bookmarks/{cafe}", headers=headers).status_code == 204
        for client in (scenes, cat):
            saved = client.get("/v1/me/bookmarks", headers=headers).json()
            assert [b["place_id"] for b in saved] == [cafe, SEED_PLACE]           # Newest first, both stores.
            assert saved[0]["name"] == "Cafe 1" and saved[0]["cover_photo"]["license"] == "CC BY-SA 4.0"
            assert saved[1]["name"] == "창경궁 대온실"
        # Removing from the other backend's mode still removes it.
        assert cat.delete(f"/v1/me/bookmarks/{SEED_PLACE}", headers=headers).status_code == 204
        assert scenes.delete(f"/v1/me/bookmarks/{cafe}", headers=headers).status_code == 204
        assert scenes.get("/v1/me/bookmarks", headers=headers).json() == []


# --- 5. 커밋은 응답 전에 ---------------------------------------------------------
def test_commit_failure_returns_an_error_instead_of_success(tmp_path):
    app = app_for("scenes", tmp_path)

    @app.post("/v1/test/deferred-violation")
    def violate(conn=DB):
        # A deferred constraint fails only at COMMIT, after the handler has returned.
        conn.execute("CREATE TEMP TABLE deferred_check (x int UNIQUE DEFERRABLE INITIALLY DEFERRED) ON COMMIT DROP")
        conn.execute("INSERT INTO deferred_check VALUES (1), (1)")
        return {"ok": True}

    @app.post("/v1/test/write")
    def write(conn=DB):
        conn.execute("INSERT INTO users (id) VALUES (%s)", (marker,))
        return {"ok": True}

    marker = str(uuid.uuid4())
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.post("/v1/test/deferred-violation").status_code == 500
        assert checked_out(app) == 0
        assert client.post("/v1/test/write").status_code == 200
    with psycopg.connect(DSN) as conn:
        assert conn.execute("SELECT 1 FROM users WHERE id=%s", (marker,)).fetchone()


# --- 3. 외부 확인 중에는 DB 연결을 잡지 않는다 ------------------------------------------
def test_provider_calls_run_without_a_checked_out_connection(tmp_path, monkeypatch):
    seen = []

    class Verifier:
        def verify(self, token, nonce=None, name=None):
            seen.append(checked_out(app))
            return Identity("kakao", "k-" + token, None, "카카오 사용자")

    app = create_app(Settings(database_url=DSN, jwt_secret=SECRET, storage_root=str(tmp_path)), verifiers={"kakao": Verifier()})
    with TestClient(app) as client:
        a = client.post("/v1/auth/kakao", json={"token": uuid.uuid4().hex})
        assert a.status_code == 200
        b = client.post("/v1/auth/kakao", json={"token": uuid.uuid4().hex}).json()
        bearer = {"Authorization": "Bearer " + b["access_token"]}
        # current_user returns its connection before the handler verifies the token to link.
        assert client.post("/v1/me/identities/kakao", headers=bearer, json={"token": "other"}).status_code == 409
        from api import growth_services
        def subscription(settings, user_id):
            seen.append(checked_out(app))
            return datetime(2099, 1, 1, tzinfo=timezone.utc), None
        monkeypatch.setattr(growth_services, "subscription", subscription)
        app.state.settings = Settings(database_url=DSN, jwt_secret=SECRET, revenuecat_secret_key="sk_test")
        assert client.post("/v1/me/billing/sync", headers=bearer).json()["premium"] is True
    assert seen == [0, 0, 0, 0]


def test_current_user_releases_its_connection_for_the_handler(tmp_path):
    app = app_for("scenes", tmp_path)
    during = []

    @app.get("/v1/test/after-auth")
    def after(user: CurrentUser = __import__("fastapi").Depends(current_user), conn=DB):
        during.append(checked_out(app))
        return {"ok": True}

    with TestClient(app) as client:
        assert client.get("/v1/test/after-auth", headers=auth(str(uuid.uuid4()))).status_code == 200
    assert during == [0]


# --- 8. 처리기가 죽은 작업 복구 ---------------------------------------------------
def test_stale_running_jobs_are_requeued_with_attempt_limit():
    from psycopg.types.json import Jsonb
    from api.worker import MAX_ATTEMPTS, recover_stale
    spot, dup = str(uuid.uuid4()), str(uuid.uuid4())
    with psycopg.connect(DSN) as conn:
        def job(status, attempts, age_s, spot_id):
            return conn.execute("""INSERT INTO jobs (kind, payload, status, attempts, locked_at)
                                   VALUES ('analyze_spot', %s, %s, %s, now() - make_interval(secs => %s)) RETURNING id""",
                                (Jsonb({"spot_id": spot_id}), status, attempts, age_s)).fetchone()[0]
        stale = job("running", 1, 7200, spot)
        fresh = job("running", 1, 10, str(uuid.uuid4()))
        exhausted = job("running", MAX_ATTEMPTS, 7200, str(uuid.uuid4()))
        covered = job("running", 1, 7200, dup)
        job("queued", 0, 0, dup)
        conn.commit()
        assert recover_stale(conn, timeout_s=3600) >= 3
        status = dict(conn.execute("SELECT id, status FROM jobs WHERE id = ANY(%s)", ([stale, fresh, exhausted, covered],)).fetchall())
        assert status == {stale: "queued", fresh: "running", exhausted: "failed", covered: "failed"}
        assert conn.execute("SELECT locked_at, attempts FROM jobs WHERE id=%s", (stale,)).fetchone() == (None, 1)
        conn.execute("DELETE FROM jobs WHERE payload->>'spot_id' = ANY(%s)", ([spot, dup],))
        conn.execute("DELETE FROM jobs WHERE id = ANY(%s)", ([fresh, exhausted],))
