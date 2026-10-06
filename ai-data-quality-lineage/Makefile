.PHONY: up down logs test
up:
	docker compose up --build
down:
	docker compose down
logs:
	docker compose logs -f
test:
	docker compose run --rm api pytest -q

