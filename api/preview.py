"""Stateless personal preview: real inputs/calculator and imported places.

Run on 127.0.0.1:8001 via npm run demo. No birth data or profiles are stored
by this service. This application is separate from the production API.
"""
from pipeline.catalog_visitors import today as kst_today

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import schemas as S, labels as L
from .catalog_models import PreviewQuery as PreviewIn
from .rate_limit import per_minute, retry_after
from saju.calculator import ForcetellerStyleCalculator

app = FastAPI(title="PhotoSpot personal preview", docs_url=None, redoc_url=None, openapi_url=None)


# Public and unauthenticated: per-IP, per-process limit (RATE_LIMIT_PREVIEW_PER_MIN, 0 disables).
rate_limits = [("/preview/", per_minute("RATE_LIMIT_PREVIEW_PER_MIN", 120))]


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    wait = retry_after(request, rate_limits)
    if wait is not None:
        return JSONResponse(status_code=429, content={"title": "요청이 너무 많아요. 잠시 후 다시 시도해 주세요", "status": 429},
                            headers={"Retry-After": str(wait)})
    return await call_next(request)


# Added after the limiter so it wraps it: 429 responses keep CORS headers.
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



def profile_card(body: PreviewIn):
    from .catalog_scoring import catalog_card
    return catalog_card(body.profile.model_dump())


@app.post("/preview/type-card", response_model=S.TypeCard)
def get_type_card(body: S.Profile):
    return profile_card(PreviewIn(profile=body, visit_date=kst_today()))


@app.post("/preview/evaluate")
def evaluate(body: PreviewIn):
    from .catalog_recommendations import recommend
    return recommend(body, profile_card(body))
