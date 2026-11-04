.PHONY: up down demo killswitch test lint typecheck migrate bootstrap

PY := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

up:
	$(PY) -m scripts.init_env
	docker compose --profile collab --profile gateway up -d --build
	$(PY) -m scripts.wait_healthy
	$(PY) -m scripts.bootstrap_switch

down:
	docker compose --profile collab --profile gateway down

demo:
	$(PY) -m scripts.replay_demo

killswitch:
	$(PY) -m scripts.killswitch_demo

test:
	$(PY) -m pytest --cov

lint:
	$(PY) -m ruff check .
	$(PY) -m black --check .

typecheck:
	$(PY) -m mypy

migrate:
	$(PY) -m alembic upgrade head

bootstrap:
	$(PY) -m scripts.bootstrap_switch
