.PHONY: api-dev agent-dev migrate test lint

api-dev:
	python -m uvicorn app.main:app --reload --app-dir services/api

agent-dev:
	python -m uvicorn app.main:app --reload --port 17321 --app-dir services/print-agent

migrate:
	cd services/api && python -m alembic upgrade head

test:
	cd services/api && python -m pytest
	cd services/print-agent && python -m pytest
	pnpm test

lint:
	python -m ruff check services
	pnpm lint

