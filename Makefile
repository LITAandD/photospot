.PHONY: up down logs test migrate openapi
up:        ## 개발 스택 실행 (DB + 마이그레이션 + API + 작업 처리기)
	docker compose up --build -d
down:
	docker compose down
logs:
	docker compose logs -f api worker
migrate:
	docker compose run --rm migrate
test:      ## 로컬에서 테스트 (DATABASE_URL 필요)
	python -m pytest tests -q
openapi:
	python -m api.export_openapi > openapi.yaml
