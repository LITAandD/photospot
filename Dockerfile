# API 서버와 작업 처리기가 같은 이미지를 쓰고, 명령만 다르다.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

FROM base AS deps
COPY requirements.txt constraints.txt ./
RUN pip install --prefix=/install -r requirements.txt

FROM base AS runtime
RUN useradd --create-home --uid 10001 app && mkdir -p /data/storage && chown -R app:app /data
COPY --from=deps /install /usr/local
COPY --chown=app:app api ./api
COPY --chown=app:app pipeline ./pipeline
COPY --chown=app:app catalog ./catalog
ENV RECOMMENDATION_BACKEND=catalog PLACE_CATALOG_DB=/app/catalog/places.sqlite3
COPY --chown=app:app saju ./saju
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app scripts ./scripts
COPY --chown=app:app schema.sql seed_example.sql ./
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=3).status == 200 else 1)"
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--no-access-log"]
