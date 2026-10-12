.PHONY: up down logs test test-python check-app quality migrate openapi
up:        ## 개발 스택 실행 (DB + 마이그레이션 + API + 작업 처리기)
	docker compose up --build -d
down:
	docker compose down
logs:
	docker compose logs -f api worker
migrate:
	docker compose run --rm migrate
test: quality test-python check-app  ## CI와 같은 핵심 검사 (DB 통합 검사는 DATABASE_URL 필요)
test-python:
	python -m pytest tests -q
quality:
	python -m scripts.check_dependencies
	python -m ruff check api pipeline saju scripts tests
	python -m mypy
check-app:
	npm --prefix client test
	npm --prefix app run typecheck
	npm --prefix app test
openapi:
	python -m api.export_openapi > openapi.yaml
