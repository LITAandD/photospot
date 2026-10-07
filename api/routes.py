"""HTTP 엔드포인트. 모든 경로는 /v1 아래."""
from __future__ import annotations

import uuid
from urllib.parse import urljoin
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from pipeline.tourapi import LocalStorage
from pipeline.place_categories import group_for

from . import labels as L
from . import schemas as S
from . import services as svc
from . import catalog_bridge
from .apple_revocation import DeleteAccountIn, revoke_for_account
from .score_display import weight_guide, photo_explanation
from .auth import CurrentUser, current_user, require_admin
from .db import get_conn

router = APIRouter(prefix="/v1")
KST = timezone(timedelta(hours=9))
DISPLAY_SOURCES = ("own_shoot", "tourapi", "owner_upload")      # 사용자 업로드는 남에게 보여주지 않음
TAG_ENUMS = {f: set(v) for f, v in L.VALUE_LABELS.items() if f != "element"}


def today_kst() -> date:
    return datetime.now(KST).date()


def _cur(conn):
    return conn.cursor(row_factory=dict_row)


def _profile(conn, user_id: str) -> dict:
    with _cur(conn) as cur:
        cur.execute("""SELECT gender::text, birth_year, height_cm::float, pc_season::text, pc_subtone::text,
                              body_type::text, mbti, calc_height_band(gender, height_cm)::text AS height_band
                         FROM user_profiles WHERE user_id = %s""", (user_id,))
        row = cur.fetchone()
        cur.execute("SELECT user_value FROM user_dimensions WHERE user_id=%s AND dimension='element'", (user_id,))
        el = cur.fetchone()
        cur.execute("SELECT wood, fire, earth, metal, water FROM user_saju WHERE user_id=%s", (user_id,))
        percents = cur.fetchone()
    base = row or {"gender": "undisclosed", "height_band": None}
    return {**base, "profile_exists": row is not None, "element": el["user_value"] if el else None,
            "saju_element": el["user_value"] if el else None,
            "saju_percents": {k: float(v) for k, v in percents.items()} if el and percents else None}


def _has_consent(conn, user_id: str, kind: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM user_consents WHERE user_id=%s AND consent_type=%s AND revoked_at IS NULL",
                    (user_id, kind))
        return cur.fetchone() is not None


def _grant(conn, user_id: str, kind: str, policy: str) -> None:
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO user_consents (user_id, consent_type, policy_version) VALUES (%s, %s, %s)
                       ON CONFLICT (user_id, consent_type) WHERE revoked_at IS NULL DO NOTHING""",
                    (user_id, kind, policy))


def _revoke(conn, user_id: str, kind: str) -> None:
    with conn.cursor() as cur:
        cur.execute("""UPDATE user_consents SET revoked_at = now()
                        WHERE user_id=%s AND consent_type=%s AND revoked_at IS NULL""", (user_id, kind))
        if kind == "saju":
            cur.execute("DELETE FROM user_saju WHERE user_id=%s", (user_id,))


def _enqueue_spot(conn, spot_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO jobs (kind, payload) VALUES ('analyze_spot', %s)
                       ON CONFLICT (kind, (payload->>'spot_id')) WHERE status = 'queued' DO NOTHING
                       RETURNING id""", (Jsonb({"spot_id": spot_id}),))
        return cur.fetchone() is not None


def _remove_uploads(conn, user_id: str) -> list[str]:
    with _cur(conn) as cur:
        cur.execute("""DELETE FROM photos WHERE uploader_id=%s AND source='user_upload'
                       RETURNING storage_path, spot_id::text""", (user_id,))
        removed = cur.fetchall()
        paths = [r["storage_path"] for r in removed]
        if paths:
            # Durable cleanup survives a process crash after the DB commit.
            cur.execute("INSERT INTO jobs (kind, payload) VALUES ('delete_files', %s)", (Jsonb({"paths": paths}),))
    for spot_id in {r["spot_id"] for r in removed}:
        _enqueue_spot(conn, spot_id)
    return paths


def _delete_files(storage: LocalStorage, paths: list[str]):
    for path in paths:
        try:
            storage.delete(path)
        except OSError:
            pass  # The durable delete_files job retries this operation.


def _scene_rows(conn, scene_ids: list[str]) -> dict[str, dict]:
    if not scene_ids:
        return {}
    with _cur(conn) as cur:
        cur.execute("""SELECT s.id::text AS id, s.spot_id::text, s.color_temp::text, s.brightness::text, s.saturation::text,
                              s.lighting::text, s.form::text, s.texture::text, s.scale::text,
                              s.crowd_level::text, s.place_character::text, s.photo_mood::text,
                              s.evidence::text, s.photo_count, s.confidence::float,
                              COALESCE(array_agg(e.element::text) FILTER (WHERE e.element IS NOT NULL), '{}') AS elements
                         FROM scenes s LEFT JOIN scene_elements e ON e.scene_id = s.id
                        WHERE s.id = ANY(%s::uuid[]) GROUP BY s.id""", (scene_ids,))
        return {r["id"]: r for r in cur.fetchall()}


def _photos(conn, request: Request, place_ids: list[str], per_place: int) -> dict[str, list[dict]]:
    if not place_ids:
        return {}
    base = urljoin(str(request.base_url), request.app.state.media_base_url).rstrip("/")
    with _cur(conn) as cur:
        cur.execute("""SELECT place_id, storage_path, source, license FROM (
                           SELECT sp.place_id::text, ph.storage_path, ph.source::text, ph.license::text,
                                  row_number() OVER (PARTITION BY sp.place_id
                                                     ORDER BY array_position(%s::text[], ph.source::text), ph.created_at) AS rn
                             FROM photos ph JOIN spots sp ON sp.id = ph.spot_id
                            WHERE sp.place_id = ANY(%s::uuid[]) AND ph.source::text = ANY(%s::text[])) t
                        WHERE rn <= %s""", (list(DISPLAY_SOURCES), place_ids, list(DISPLAY_SOURCES), per_place))
        out: dict[str, list[dict]] = {}
        for r in cur.fetchall():
            attribution, keep = svc.photo_attribution(r["source"], r["license"])
            out.setdefault(r["place_id"], []).append(
                {"url": f"{base}/{r['storage_path']}", "attribution": attribution,
                 "license": r["license"], "keep_aspect_ratio": keep})
        return out


def _links(conn, place_ids: list[str]) -> dict[str, dict]:
    out = {pid: {} for pid in place_ids}
    if not place_ids:
        return out
    with _cur(conn) as cur:
        cur.execute("""SELECT place_id::text, provider::text, external_id, url FROM place_external_ids
                        WHERE place_id = ANY(%s::uuid[])""", (place_ids,))
        for r in cur.fetchall():
            d = out[r["place_id"]]
            if r["provider"] == "naver":
                d["naver_map_url"] = r["url"]
            elif r["provider"] == "google":
                d["google_place_id"] = r["external_id"]
            elif r["provider"] == "kakao":
                d["kakao_place_id"] = r["external_id"]
    return out


def _missing(profile: dict) -> list[str]:
    names = [("pc_season", "퍼스널컬러"), ("body_type", "체형"), ("height_cm", "키"), ("mbti", "MBTI")]
    return [label for key, label in names if not profile.get(key)]


# ---------------------------------------------------------------------------
@router.get("/health", tags=["system"])
def health(conn=Depends(get_conn)):
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
    return {"ok": True}


# --- 프로필 · 동의 · 사주 ------------------------------------------------------
@router.get("/me/profile", response_model=S.ProfileOut, tags=["me"])
def get_profile(user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    p = _profile(conn, user.id)
    return {**{k: v for k, v in p.items() if k != "element"}, "saju_enabled": p["element"] is not None}


@router.put("/me/profile", response_model=S.ProfileOut, tags=["me"])
def put_profile(body: S.Profile, request: Request, user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    d = body.model_dump()
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO user_profiles (user_id, gender, birth_year, height_cm, pc_season, pc_subtone, body_type, mbti)
                       VALUES (%(u)s, %(gender)s, %(birth_year)s, %(height_cm)s, %(pc_season)s, %(pc_subtone)s, %(body_type)s, %(mbti)s)
                       ON CONFLICT (user_id) DO UPDATE SET gender=EXCLUDED.gender, birth_year=EXCLUDED.birth_year,
                         height_cm=EXCLUDED.height_cm, pc_season=EXCLUDED.pc_season, pc_subtone=EXCLUDED.pc_subtone,
                         body_type=EXCLUDED.body_type, mbti=EXCLUDED.mbti, updated_at=now()""", {**d, "u": user.id})
    _grant(conn, user.id, "style_profile", request.app.state.settings.policy_version)
    return get_profile(user, conn)


@router.post("/me/consents", status_code=204, tags=["me"])
def grant_consent(body: S.ConsentIn, request: Request, user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    _grant(conn, user.id, body.type, request.app.state.settings.policy_version)


@router.delete("/me/consents/{consent_type}", status_code=204, tags=["me"])
def revoke_consent(consent_type: S.ConsentType, request: Request, user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    _revoke(conn, user.id, consent_type)
    if consent_type == "style_profile":
        conn.execute("DELETE FROM user_profiles WHERE user_id=%s", (user.id,))
    if consent_type == "photo_analysis":
        paths = _remove_uploads(conn, user.id)
        conn.commit()
        _delete_files(request.app.state.storage, paths)


@router.put("/me/saju", response_model=S.SajuOut, tags=["me"],
            responses={400: {"model": S.Problem}, 503: {"model": S.Problem}})
def put_saju(body: S.SajuIn, request: Request, user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    if not body.consent:
        raise HTTPException(400, "사주 계산에는 동의가 필요해요")
    try:
        kwargs = {"birth_hour_branch": body.birth_hour_branch} if body.birth_hour_branch else {}
        result = request.app.state.saju_calculator.calculate(body.birth_date, body.birth_time, body.calendar, body.leap_month, **kwargs)
    except NotImplementedError as e:
        raise HTTPException(503, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    # body(생년월일시)와 네 기둥은 응답에만 쓰고 어디에도 저장·로그하지 않는다
    pct, dom = result.elements.percents, result.dominant
    has_time = body.birth_time is not None or body.birth_hour_branch is not None
    _grant(conn, user.id, "saju", request.app.state.settings.policy_version)
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO user_saju (user_id, has_birth_time, wood, fire, earth, metal, water,
                                              dominant_element, method, calc_version)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (user_id) DO UPDATE SET has_birth_time=EXCLUDED.has_birth_time, wood=EXCLUDED.wood,
                         fire=EXCLUDED.fire, earth=EXCLUDED.earth, metal=EXCLUDED.metal, water=EXCLUDED.water,
                         dominant_element=EXCLUDED.dominant_element, method=EXCLUDED.method,
                         calc_version=EXCLUDED.calc_version, created_at=now()""",
                    (user.id, has_time, *[pct[e] for e in svc.ELEMENT_ORDER], dom, "forceteller_v1", "v1"))
    return {"method": "forceteller_v1", "percents": pct, "dominant_element": dom,
            "dominant_label": L.VALUE_LABELS["element"][dom], "pillars": result.pillars.as_dict(),
            "corrections": result.elements.corrections, "has_birth_time": has_time}


@router.delete("/me/saju", status_code=204, tags=["me"])
def delete_saju(user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    _revoke(conn, user.id, "saju")


@router.get("/me/type-card", response_model=S.TypeCard, tags=["me"])
def get_type_card(user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    p = _profile(conn, user.id)
    with _cur(conn) as cur:
        cur.execute("""SELECT r.attribute, r.attr_value, r.score FROM match_rules r
                         JOIN user_dimensions d ON d.dimension = r.dimension AND d.user_value = r.user_value
                        WHERE d.user_id = %s AND r.dimension IN ('pc_season', 'pc_tone', 'body_type')
                        ORDER BY r.dimension, r.score DESC""", (user.id,))
        rules = cur.fetchall()
    return svc.type_card(p, None, rules)


@router.delete("/me", status_code=204, tags=["me"])
def delete_account(request: Request, body: DeleteAccountIn | None = None, user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    """탈퇴: 계정 행은 '탈퇴' 표시로 남겨 같은 토큰을 막고, 개인정보는 모두 삭제.
    본인이 올린 사진(얼굴이 있을 수 있음)은 파일까지 지우고 영향받은 장면은 재집계."""
    storage: LocalStorage = request.app.state.storage
    conn.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (user.id,))
    revoke_for_account(request, conn, user.id, body)
    paths = _remove_uploads(conn, user.id)
    with _cur(conn) as cur:
        cur.execute('SELECT id FROM app_feedback WHERE user_id=%s FOR UPDATE', (user.id,))
        cur.fetchall()  # Wait for any in-flight AI analysis before removing its derived data.
        cur.execute('DELETE FROM feedback_triages WHERE feedback_ids && ARRAY(SELECT id FROM app_feedback WHERE user_id=%s)', (user.id,))
        for table in ("app_feedback", "social_oauth_states", "social_connections", "billing_entitlements", "campaign_events", "user_profiles", "user_saju", "user_consents", "recommendations", "apple_grants", "auth_identities", "refresh_tokens", "bookmarks", "catalog_bookmarks"):
            cur.execute(f"DELETE FROM {table} WHERE user_id = %s", (user.id,))
        cur.execute("UPDATE users SET deleted_at = now() WHERE id = %s", (user.id,))
    conn.commit()
    _delete_files(storage, paths)
    return Response(status_code=204)


# --- 저장한 장소 -------------------------------------------------------------
@router.get("/me/bookmarks", response_model=list[S.Bookmark], tags=["me"])
def bookmarks(request: Request, user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    if catalog_bridge.enabled(request): return catalog_bridge.bookmarks(conn, user.id)
    with _cur(conn) as cur:
        cur.execute("""SELECT p.id::text AS place_id, p.name, p.address FROM bookmarks b
                         JOIN places p ON p.id=b.place_id WHERE b.user_id=%s AND p.status <> 'closed'
                         ORDER BY b.created_at DESC LIMIT 500""", (user.id,))
        rows = cur.fetchall()
    photos = _photos(conn, request, [r["place_id"] for r in rows], 1)
    return [{**r, "cover_photo": (photos.get(r["place_id"]) or [None])[0]} for r in rows]


@router.put("/me/bookmarks/{place_id}", status_code=204, tags=["me"])
def save_bookmark(place_id: uuid.UUID, request: Request, user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    if catalog_bridge.enabled(request):
        catalog_bridge.find(place_id)
        conn.execute('INSERT INTO catalog_bookmarks (user_id,place_id) VALUES (%s,%s) ON CONFLICT DO NOTHING', (user.id,place_id))
        return
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM places WHERE id=%s AND status <> 'closed'", (place_id,))
        if not cur.fetchone():
            raise HTTPException(404, "장소를 찾을 수 없어요")
        cur.execute("INSERT INTO bookmarks (user_id, place_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (user.id, place_id))


@router.delete("/me/bookmarks/{place_id}", status_code=204, tags=["me"])
def remove_bookmark(place_id: uuid.UUID, request: Request, user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    if catalog_bridge.enabled(request):
        conn.execute('DELETE FROM catalog_bookmarks WHERE user_id=%s AND place_id=%s', (user.id,place_id))
        return
    conn.execute("DELETE FROM bookmarks WHERE user_id=%s AND place_id=%s", (user.id, place_id))


# --- 추천 -------------------------------------------------------------------
@router.get("/recommendations", response_model=S.RecommendationList, tags=["recommend"])
def recommend(request: Request,
              lat: float = Query(..., ge=33, le=39, description="대한민국 범위"),
              lng: float = Query(..., ge=124, le=132),
              visit_date: date | None = Query(None, alias="date"),
              radius_m: int = Query(5000, ge=500),
              time_slot: S.TimeSlot | None = None,
              use_saju: bool = False,
              place_group: S.PlaceGroup = "all",
              limit: int = Query(30, ge=1, le=50),
              photo_only: bool = False,
              min_fit: int = Query(0, ge=0, le=100),
              user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    visit = visit_date or today_kst()
    radius = min(radius_m, request.app.state.settings.max_radius_m)
    if photo_only or min_fit:
        from .growth_routes import billing_status
        if not billing_status(conn, request.app.state.settings, user.id)['premium']:
            raise HTTPException(403, '추가 필터는 포토스팟 Plus 구독이 필요해요')
        if not catalog_bridge.enabled(request): raise HTTPException(503, '추가 추천 필터를 준비 중이에요')
    p = _profile(conn, user.id)
    if catalog_bridge.enabled(request):
        return catalog_bridge.evaluate(p, visit, lat=lat, lng=lng, radius_m=radius, time_slot=time_slot,
                                       use_saju=use_saju, place_group=place_group, limit=limit, photo_only=photo_only, min_fit=min_fit)['recommendations']
    daily = svc.daily_context(visit, p["element"], use_saju, p["saju_percents"])
    day_element = daily["day_element"] if daily else None
    with _cur(conn) as cur:
        cur.execute("""SELECT r.*, p.category::text AS category FROM recommend_places_near(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) r
                       JOIN places p ON p.id=r.place_id ORDER BY r.total DESC, r.distance_m ASC, r.place_id""",
                    (user.id, visit, lat, lng, radius, limit, time_slot, bool(daily), day_element, place_group))
        rows = cur.fetchall()
        cur.execute("SELECT version FROM score_settings WHERE is_active")
        version = cur.fetchone()["version"]
        cur.execute("SELECT dimension, attribute, weight, layer FROM score_weights WHERE version=%s ORDER BY dimension, attribute", (version,))
        weights = cur.fetchall()
    scenes = _scene_rows(conn, [str(r["scene_id"]) for r in rows])
    place_ids = [str(r["place_id"]) for r in rows]
    covers, links = _photos(conn, request, place_ids, 1), _links(conn, place_ids)
    items = []
    with conn.cursor() as cur:
        for r in rows:
            sid, pid = str(r["scene_id"]), str(r["place_id"])
            cur.execute("""INSERT INTO recommendations (user_id, scene_id, weights_version, total, breakdown, visit_date)
                           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (user.id, sid, version, r["total"], Jsonb(r["breakdown"]), visit))
            sc = scenes[sid]
            items.append({
                "recommendation_id": cur.fetchone()[0], "place_id": pid, "place_name": r["place_name"],
                "place_group": group_for(r["category"]),
                "spot_id": sc["spot_id"], "scene_id": sid,
                "spot_name": r["spot_name"], "time_slot": r["time_slot"], "time_slot_label": L.TIME_SLOT[r["time_slot"]],
                "score": float(r["total"]),
                "scoring": photo_explanation(weights, r["breakdown"], r["total"]),
                "recommended_elements": svc.recommended_elements(sc["elements"], daily),
                "practical_score": float(r["practical"]) if r["practical"] is not None else None,
                "distance_m": r["distance_m"],
                "reasons": svc.reasons(r["breakdown"], sc, sc["elements"], None, top=8, day_element=day_element,
                                       deficient=daily["deficient_elements"] if daily else None),
                "cover_photo": (covers.get(pid) or [None])[0], "links": links[pid]})
    return {"visit_date": visit, "radius_m": radius, "items": items, "missing_inputs": _missing(p), "daily": daily, "place_group": place_group,
            "score_weights": weight_guide(weights)}


@router.get("/places/{place_id}", response_model=S.PlaceDetail, tags=["recommend"], responses={404: {"model": S.Problem}})
def place_detail(place_id: uuid.UUID, request: Request, visit_date: date | None = Query(None, alias="date"),
                 use_saju: bool = False,
                 user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    visit, pid = visit_date or today_kst(), str(place_id)
    p = _profile(conn, user.id)
    if catalog_bridge.enabled(request):
        place = catalog_bridge.find(pid)
        return catalog_bridge.evaluate(p, visit, lat=place['lat'], lng=place['lng'],
                                       use_saju=use_saju, place_ids=[pid])['places'][pid]
    daily = svc.daily_context(visit, p["element"], use_saju, p["saju_percents"])
    day_element = daily["day_element"] if daily else None
    with _cur(conn) as cur:
        cur.execute("SELECT name, category::text, address, is_open_on(id, %s) AS open FROM places WHERE id=%s AND status <> 'closed'",
                    (visit, pid))
        place = cur.fetchone()
        if not place:
            raise HTTPException(404, "장소를 찾을 수 없어요")
        cur.execute("SELECT * FROM score_scenes_in(%s, %s, ARRAY[%s]::uuid[], %s, %s)", (user.id, visit, pid, bool(daily), day_element))
        scored = cur.fetchall()
        cur.execute("""SELECT count(*) FILTER (WHERE NOT scene_scorable(s, cfg)) AS pending, count(*) FILTER (WHERE scene_scorable(s, cfg)) AS ready
                         FROM scenes s JOIN spots sp ON sp.id = s.spot_id
                        CROSS JOIN (SELECT * FROM score_settings WHERE is_active) cfg
                        WHERE sp.place_id = %s""", (pid,))
        counts = cur.fetchone()
        pending, ready = counts["pending"], counts["ready"]
        cur.execute("""SELECT rule_type::text, weekday, start_md, end_md, start_date, end_date
                         FROM operating_rules WHERE place_id=%s ORDER BY id""", (pid,))
        rules = cur.fetchall()
        cur.execute("SELECT w.dimension, w.attribute, w.weight, w.layer FROM score_weights w JOIN score_settings s ON s.version=w.version WHERE s.is_active ORDER BY w.dimension, w.attribute")
        weights = cur.fetchall()
    scenes = _scene_rows(conn, [str(s["scene_id"]) for s in scored])

    def to_out(s):
        sc = scenes[str(s["scene_id"])]
        return {"scene_id": str(s["scene_id"]), "spot_id": sc["spot_id"], "spot_name": s["spot_name"], "time_slot": s["time_slot"],
                "season": s["season"], "score": float(s["total"]), "passed": s["passed"],
                "recommended_elements": svc.recommended_elements(sc["elements"], daily),
                "evidence": sc["evidence"], "photo_count": sc["photo_count"], "confidence": sc["confidence"],
                "scoring": photo_explanation(weights, s["breakdown"], s["total"]),
                "reasons": svc.reasons(s["breakdown"], sc, sc["elements"], None, top=8, day_element=day_element,
                                       deficient=daily["deficient_elements"] if daily else None)}

    outs = sorted((to_out(s) for s in scored), key=lambda x: (not x["passed"], -x["score"]))
    best = outs[0] if outs and outs[0]["passed"] else None
    tips = svc.tips(p, p.get("height_band"), scenes[best["scene_id"]]) if best else []
    notes = svc.visit_notes(rules)
    if not place["open"]:
        notes.insert(0, "방문일에는 운영하지 않아요")
    return {"place_id": pid, "name": place["name"], "category": place["category"], "address": place["address"],
            "place_group": group_for(place["category"]),
            "best_scene": best, "other_scenes": [o for o in outs if o is not best], "tips": tips,
            "visit_notes": notes, "open_on_visit_date": place["open"],
            "photos": _photos(conn, request, [pid], 10).get(pid, []), "links": _links(conn, [pid])[pid],
            "analysis_pending": ready == 0 and pending > 0,
            "recommended_elements": best["recommended_elements"] if best else [],
            "score_weights": weight_guide(weights)}


@router.post("/recommendations/{rec_id}/feedback", status_code=201, tags=["recommend"],
             responses={404: {"model": S.Problem}, 422: {"model": S.Problem}})
def feedback(rec_id: int, body: S.FeedbackIn, user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    for k, v in (body.tag_corrections or {}).items():
        if v not in TAG_ENUMS.get(k, set()):
            raise HTTPException(422, f"알 수 없는 태그 수정: {k}={v}")
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM recommendations WHERE id=%s AND user_id=%s", (rec_id, user.id))
        if not cur.fetchone():
            raise HTTPException(404, "추천 기록을 찾을 수 없어요")
        if body.photo_id:
            cur.execute("""SELECT 1 FROM photos ph JOIN recommendations r ON r.id=%s
                             JOIN scenes s ON s.id=r.scene_id
                            WHERE ph.id=%s AND ph.uploader_id=%s AND ph.source='user_upload'
                              AND ph.spot_id=s.spot_id""", (rec_id, body.photo_id, user.id))
            if not cur.fetchone():
                raise HTTPException(404, "이 추천 장소에 직접 올린 사진만 연결할 수 있어요")
        cur.execute("""INSERT INTO recommendation_feedback (recommendation_id, visited, rating, photo_id, tag_corrections)
                       VALUES (%s,%s,%s,%s,%s)
                       ON CONFLICT (recommendation_id) DO UPDATE SET visited=EXCLUDED.visited, rating=EXCLUDED.rating,
                         photo_id=EXCLUDED.photo_id, tag_corrections=EXCLUDED.tag_corrections""",
                    (rec_id, body.visited, body.rating, body.photo_id,
                     Jsonb(body.tag_corrections) if body.tag_corrections else None))
    return {"ok": True}


# --- 사진 업로드 ---------------------------------------------------------------
@router.post("/photos", status_code=202, response_model=S.PhotoAccepted, tags=["photos"],
             responses={403: {"model": S.Problem}, 413: {"model": S.Problem}, 415: {"model": S.Problem}})
def upload_photo(request: Request, spot_id: uuid.UUID = Form(...), file: UploadFile = File(...),
                       user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    settings = request.app.state.settings
    if not _has_consent(conn, user.id, "photo_analysis"):
        raise HTTPException(403, "사진 분석 동의가 필요해요")
    data = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"사진은 {settings.max_upload_mb}MB까지 올릴 수 있어요")
    try:
        clean, taken = svc.sanitize_photo(data)
    except ValueError as e:
        raise HTTPException(415, str(e))
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM spots WHERE id=%s", (str(spot_id),))
        if not cur.fetchone():
            raise HTTPException(404, "스팟을 찾을 수 없어요")
        path = request.app.state.storage.save(f"user/{uuid.uuid4().hex}.jpg", clean)
        cur.execute("""INSERT INTO photos (spot_id, source, license, uploader_id, storage_path, taken_at)
                       VALUES (%s, 'user_upload', 'user_consent', %s, %s, %s) RETURNING id::text""",
                    (str(spot_id), user.id, path, taken.replace(tzinfo=KST) if taken else None))
        photo_id = cur.fetchone()[0]
    queued = _enqueue_spot(conn, str(spot_id))
    return {"photo_id": photo_id, "job_queued": queued, "taken_at": taken.isoformat() if taken else None}


# --- 자가진단 -----------------------------------------------------------------
DiagKind = S.Literal["personal-color", "body-type"]


@router.get("/diagnosis/{kind}/questions", response_model=list[S.DiagnosisQuestion], tags=["diagnosis"])
def diagnosis_questions(kind: DiagKind):
    return svc.diagnosis_questions(kind)


@router.post("/diagnosis/{kind}", response_model=S.DiagnosisOut, tags=["diagnosis"])
def diagnosis(kind: DiagKind, body: S.DiagnosisIn):
    try:
        return svc.diagnose(kind, body.answers)
    except ValueError as e:
        raise HTTPException(422, str(e))


# --- 검수 (관리자) -------------------------------------------------------------
@router.get("/admin/review-queue", response_model=list[S.ReviewItem], tags=["admin"])
def review_queue(limit: int = Query(50, ge=1, le=200), _: CurrentUser = Depends(require_admin), conn=Depends(get_conn)):
    """자동 태깅 신뢰도가 낮은 장면 + 최근 90일 사용자 태그 수정 제보가 3건 이상인 장면."""
    with _cur(conn) as cur:
        cur.execute("""
            WITH reports AS (
                -- 마지막 검수 이후에 들어온 제보만 센다 (검수가 곧 제보 처리)
                SELECT r.scene_id, count(*) AS n FROM recommendation_feedback f
                  JOIN recommendations r ON r.id = f.recommendation_id
                  JOIN scenes sc ON sc.id = r.scene_id
                 WHERE f.tag_corrections IS NOT NULL
                   AND f.created_at > GREATEST(COALESCE(sc.verified_at, '-infinity'), now() - interval '90 days')
                 GROUP BY r.scene_id HAVING count(*) >= 3)
            SELECT s.id::text AS scene_id, p.name AS place_name, sp.name AS spot_name, s.time_slot::text,
                   s.season::text, s.confidence::float, s.photo_count,
                   COALESCE(s.review_reasons, '{}') || CASE WHEN rp.n IS NOT NULL
                       THEN ARRAY['사용자 태그 수정 제보 ' || rp.n || '건'] ELSE '{}'::text[] END AS reasons
              FROM scenes s JOIN spots sp ON sp.id = s.spot_id JOIN places p ON p.id = sp.place_id
              LEFT JOIN reports rp ON rp.scene_id = s.id
             WHERE rp.n IS NOT NULL
                OR (s.tag_source = 'auto' AND s.verified_at IS NULL
                    AND (s.confidence < 0.6 OR cardinality(s.review_reasons) > 0))
             ORDER BY rp.n DESC NULLS LAST, s.confidence ASC NULLS FIRST
             LIMIT %s""", (limit,))
        return cur.fetchall()


@router.patch("/admin/scenes/{scene_id}", status_code=204, tags=["admin"], responses={404: {"model": S.Problem}})
def edit_scene(scene_id: uuid.UUID, body: S.SceneEdit, admin: CurrentUser = Depends(require_admin), conn=Depends(get_conn)):
    fields = {k: v for k, v in body.model_dump(exclude={"elements", "verify"}).items() if v is not None}
    sets = [f"{k} = %({k})s" for k in fields]
    if body.verify:
        sets += ["tag_source = 'verified'", "evidence = 'human'", "verified_at = now()", "verified_by = %(admin)s", "review_reasons = '{}'"]
    elif fields:
        sets += ["tag_source = 'manual'", "evidence = 'human'"]
    params = {**fields, "admin": admin.id, "id": str(scene_id)}
    with conn.cursor() as cur:
        if sets:
            cur.execute(f"UPDATE scenes SET {', '.join(sets)} WHERE id = %(id)s RETURNING id", params)
        else:
            cur.execute("SELECT id FROM scenes WHERE id = %(id)s", params)
        if not cur.fetchone():
            raise HTTPException(404, "장면을 찾을 수 없어요")
        if body.elements is not None:
            cur.execute("DELETE FROM scene_elements WHERE scene_id = %s", (str(scene_id),))
            for e in body.elements:
                cur.execute("INSERT INTO scene_elements (scene_id, element) VALUES (%s, %s)", (str(scene_id), e))
    return Response(status_code=204)
