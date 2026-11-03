.PHONY: up down demo killswitch test lint typecheck migrate bootstrap

up:
	python scripts/init_env.py
	docker compose --profile collab --profile gateway up -d --build
	python scripts/wait_healthy.py
	python scripts/bootstrap_switch.py

down:
	docker compose --profile collab --profile gateway down

demo:
	python -m scripts.replay_demo

killswitch:
	python -m scripts.killswitch_demo

test:
	pytest --cov

lint:
	ruff check .
	black --check .

typecheck:
	mypy

migrate:
	alembic upgrade head

bootstrap:
	python scripts/bootstrap_switch.py
