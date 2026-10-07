"""Stateless personal preview: real inputs/calculator and imported places.

Run on 127.0.0.1:8001 via npm run demo. No birth data or profiles are stored
by this service. This application is separate from the production API.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import math

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import schemas as S, services as svc, labels as L
from .preview_catalog import PLACES, SCENES, RULES, WEIGHTS, OPERATING_RULES
from saju.calculator import ForcetellerStyleCalculator

app = FastAPI(title="PhotoSpot personal preview", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:8081", "http://127.0.0.1:8081"],
                   allow_methods=["POST", "GET"], allow_headers=["Content-Type"])


@app.middleware("http")
async def private_response(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Do not echo sensitive birth inputs in validation errors/logs.
    return JSONResponse(status_code=422, content={"title": "입력값을 확인해 주세요", "status": 422,
                        "detail": "; ".join(e["msg"] for e in exc.errors())})


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"title": str(exc.detail), "status": exc.status_code})


@app.get("/health")
def health():
    return {"ok": True, "mode": "personal-preview"}


def height_band(profile):
    height = profile.get("height_cm")
    if height is None:
        return None
    low, high = {"female": (157, 167), "male": (170, 180)}.get(profile.get("gender"), (163, 174))
    return "small" if height < low else "tall" if height >= high else "medium"


@app.post("/preview/profile", response_model=S.ProfileOut)
def validate_profile(body: S.Profile):
    p = body.model_dump()
    return {**p, "height_band": height_band(p), "profile_exists": True}


@app.post("/preview/saju", response_model=S.SajuOut)
def calculate_saju(body: S.SajuIn):
    if not body.consent:
        raise HTTPException(400, "사주 계산에는 동의가 필요해요")
    result = ForcetellerStyleCalculator().calculate(body.birth_date, body.birth_time, body.calendar, body.leap_month, body.birth_hour_branch)
    return {"method": "forceteller_v1", "percents": result.elements.percents,
            "dominant_element": result.dominant, "dominant_label": L.VALUE_LABELS["element"][result.dominant],
            "pillars": result.pillars.as_dict(), "corrections": result.elements.corrections,
            "has_birth_time": body.birth_time is not None or body.birth_hour_branch is not None}


from .catalog_models import CatalogQuery as PreviewIn


def dimensions(profile, daily):
    d = {k: profile[k] for k in ("pc_season", "body_type") if profile.get(k)}
    if profile.get("pc_season"):
        tone = profile.get("pc_subtone")
        d["pc_tone"] = tone if tone and tone != "true" else f"default_{profile['pc_season']}"
    if height_band(profile):
        d["height_band"] = height_band(profile)
    if profile.get("mbti"):
        d.update(zip(["mbti_ei", "mbti_sn", "mbti_tf"], profile["mbti"][:3]))
    if daily:
        d["day_element"] = daily["day_element"]
        if daily["deficient_elements"]:
            d["element"] = daily["deficient_elements"]
    return d


def rounded(value):
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def score_scene(scene, dims):
    parts = []
    for w in [*WEIGHTS, {"dimension": "day_element", "attribute": "element", "weight": 4, "layer": "auxiliary"}]:
        dim, attr, weight = w["dimension"], w["attribute"], w["weight"]
        if dim not in dims:
            continue
        if dim == "element":
            score = int(bool(set(dims[dim]) & set(scene["elements"])))
        elif dim == "day_element":
            score = int(dims[dim] in scene["elements"])
        else:
            values = scene["elements"] if attr == "element" else [scene.get(attr)]
            score = max((r["score"] for r in RULES if r["dimension"] == dim and r["user_value"] == dims[dim]
                         and r["attribute"] == attr and r["attr_value"] in values), default=0)
        parts.append({**w, "score": score, "points": score * weight})
    def total(rows):
        return rounded(100 * sum(r["points"] for r in rows) / sum(r["weight"] for r in rows)) if rows else None
    practical = total([r for r in parts if r["layer"] == "practical"])
    return {"score": total(parts) or 0, "practical": practical, "passed": practical is None or practical >= 10,
            "breakdown": {f"{r['dimension']}.{r['attribute']}": r["points"] for r in parts}}


def is_open(pid, visit):
    rules = [r for r in OPERATING_RULES if r["place_id"] == pid]
    for rule in rules:
        if rule["rule_type"] == "weekly_closed" and (visit.weekday() + 1) % 7 == rule["weekday"]:
            return False
        if rule["rule_type"] == "open_period" and not rule["start_md"] <= visit.strftime("%m-%d") <= rule["end_md"]:
            return False
    return True


def distance(lat, lng, place):
    a, b = math.radians(lat), math.radians(place["lat"])
    h = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(place["lng"]-lng)/2)**2
    return round(6371000 * 2 * math.asin(min(1, math.sqrt(h))))


def profile_card(body: PreviewIn):
    from .catalog_scoring import catalog_card
    return catalog_card(body.profile.model_dump())


@app.post("/preview/type-card", response_model=S.TypeCard)
def get_type_card(body: S.Profile):
    return profile_card(PreviewIn(profile=body, visit_date=date.today()))


@app.post("/preview/evaluate")
def evaluate(body: PreviewIn):
    from .catalog_recommendations import recommend
    return recommend(body, profile_card(body))


def evaluate_sample(body: PreviewIn):
    """Deterministic SQL parity regression fixture only; not an HTTP endpoint."""
    p = body.profile.model_dump()
    daily = svc.daily_context(body.visit_date, body.element, body.use_saju, body.percents)
    dims = dimensions(p, daily)
    card_rules = sorted([r for r in RULES if r["dimension"] in ("pc_season", "pc_tone", "body_type")
                         and dims.get(r["dimension"]) == r["user_value"]], key=lambda r: (r["dimension"], -r["score"]))
    card = svc.type_card(p, None, card_rules)
    places, items = {}, []
    season = ["winter", "winter", "spring", "spring", "spring", "summer", "summer", "summer", "autumn", "autumn", "autumn", "winter"][body.visit_date.month-1]
    for scene in SCENES:
        pid = scene["place_id"]
        place = PLACES[pid]
        result = score_scene(scene, dims)
        eligible = is_open(pid, body.visit_date) and scene["season"] in ("all", season)
        if daily and daily["deficient_elements"]:
            eligible = eligible and bool(set(daily["deficient_elements"]) & set(scene["elements"]))
        reasons = svc.reasons(result["breakdown"], scene, scene["elements"], None, top=8,
                              day_element=dims.get("day_element"), deficient=daily["deficient_elements"] if daily else None)
        scored = {"scene_id": scene["id"], "spot_id": scene["spot_id"], "spot_name": scene["spot_name"],
                  "recommended_elements": svc.recommended_elements(scene["elements"], daily),
                  "time_slot": scene["time_slot"], "season": scene["season"], "score": result["score"],
                  "passed": result["passed"], "evidence": "human", "photo_count": 0, "confidence": None, "reasons": reasons}
        best = scored if eligible and result["passed"] else None
        places[pid] = {"place_id": pid, "name": place["name"], "category": place["category"], "address": None,
                       "best_scene": best, "other_scenes": [scored] if eligible and not best else [],
                       "tips": svc.tips(p, height_band(p), scene) if best else [], "photos": [], "links": {},
                       "visit_notes": (["촬영일에는 샘플 운영 조건에 맞지 않아요"] if not eligible else []) +
                           ["체험용 샘플 태그예요. 실제 운영·촬영 여건은 방문 전 확인해 주세요."],
                       "open_on_visit_date": is_open(pid, body.visit_date), "analysis_pending": False,
                       "recommended_elements": scored["recommended_elements"]}
        dist = distance(body.lat, body.lng, place)
        if not best or dist > body.radius_m or body.time_slot and scene["time_slot"] != body.time_slot:
            continue
        items.append({"recommendation_id": int(scene["id"][-3:]), "place_id": pid, "place_name": place["name"],
                      "recommended_elements": scored["recommended_elements"],
                      "scene_id": scene["id"], "spot_id": scene["spot_id"], "spot_name": scene["spot_name"],
                      "time_slot": scene["time_slot"], "time_slot_label": L.TIME_SLOT[scene["time_slot"]],
                      "score": result["score"], "practical_score": result["practical"], "distance_m": dist,
                      "reasons": reasons, "cover_photo": None, "links": {}})
    items.sort(key=lambda i: (-i["score"], i["distance_m"]))
    rec = {"visit_date": body.visit_date, "radius_m": body.radius_m, "items": items, "daily": daily,
           "missing_inputs": [label for key, label in [("pc_season", "퍼스널컬러"), ("body_type", "체형"), ("height_cm", "키"), ("mbti", "MBTI")] if not p.get(key)]}
    return {"card": S.TypeCard.model_validate(card), "recommendations": S.RecommendationList.model_validate(rec),
            "places": {k: S.PlaceDetail.model_validate(v) for k, v in places.items()}}
