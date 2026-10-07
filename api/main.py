"""앱 진입점: uvicorn api.main:app"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from psycopg import OperationalError
from psycopg_pool import PoolTimeout

from pipeline.tourapi import LocalStorage

from .config import Settings
from .db import get_conn, init_pool
from .auth_routes import router as auth_router
from .growth_routes import router as growth_router
from .providers import build_verifiers
from .apple_revocation import AppleRevoker
from .routes import router
from saju.calculator import ForcetellerStyleCalculator

from .services import ElementCalculator


def create_app(settings: Settings | None = None, saju_calculator: ElementCalculator | None = None,
               verifiers: dict | None = None) -> FastAPI:
    settings = settings or Settings()
    @asynccontextmanager
    async def lifespan(app):
        app.state.pool.open()
        yield
        app.state.pool.close()

    app = FastAPI(title="포토스팟 추천 API", version="1.2.0", lifespan=lifespan,
                  description="퍼스널컬러·체형 기반 사진 명소 추천. 소셜 로그인(/v1/auth/*)으로 받은 액세스 토큰을 Bearer로 보낸다.")
    app.state.settings = settings
    app.state.storage = LocalStorage(settings.storage_root)
    app.state.media_base_url = os.environ.get("MEDIA_BASE_URL", "/media")
    app.state.saju_calculator = saju_calculator or ForcetellerStyleCalculator()
    app.state.pool = init_pool(settings.database_url)
    # 웹 앱(다른 출처)에서 호출할 때 필요. 운영에서는 CORS_ORIGINS=https://app.example.com 처럼 제한
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Authorization", "Content-Type"])
    app.state.verifiers = verifiers if verifiers is not None else build_verifiers(settings)
    app.state.apple_revoker = AppleRevoker(settings, app.state.verifiers.get('apple'))
    app.include_router(auth_router)
    app.include_router(growth_router)
    app.include_router(router)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/v1/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/media/{path:path}", include_in_schema=False)
    def public_photo(path: str, conn=Depends(get_conn)):
        # Never mount STORAGE_ROOT: it also contains private user uploads.
        with conn.cursor() as cur:
            cur.execute("""SELECT 1 FROM photos WHERE storage_path=%s
                           AND source IN ('own_shoot', 'tourapi', 'owner_upload') LIMIT 1""", (path,))
            if not cur.fetchone():
                raise HTTPException(404, "사진을 찾을 수 없어요")
        try:
            full = app.state.storage.open_path(path)
        except ValueError:
            raise HTTPException(404, "사진을 찾을 수 없어요")
        if not Path(full).is_file():
            raise HTTPException(404, "사진을 찾을 수 없어요")
        return FileResponse(full, headers={"Cache-Control": "public, max-age=3600"})

    @app.exception_handler(HTTPException)
    def problem(request: Request, exc: HTTPException):
        return JSONResponse({"type": "about:blank", "title": exc.detail, "status": exc.status_code},
                            status_code=exc.status_code, media_type="application/problem+json", headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    def invalid(request: Request, exc: RequestValidationError):
        # Pydantic errors can contain ValueError objects and sensitive input values.
        detail = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        return JSONResponse({"type": "about:blank", "title": "요청 값이 올바르지 않아요", "status": 422,
                             "detail": detail}, status_code=422, media_type="application/problem+json")

    @app.exception_handler(PoolTimeout)
    @app.exception_handler(OperationalError)
    def unavailable(request: Request, exc: Exception):
        return JSONResponse({"type": "about:blank", "title": "서버 연결을 잠시 후 다시 시도해 주세요", "status": 503},
                            status_code=503, media_type="application/problem+json")

    return app


app = create_app()
