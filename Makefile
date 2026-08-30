.PHONY: dev test lint frontend

VENV_BIN := .venv/bin
PYTEST := $(if $(wildcard $(VENV_BIN)/pytest),$(VENV_BIN)/pytest,pytest)
RUFF := $(if $(wildcard $(VENV_BIN)/ruff),$(VENV_BIN)/ruff,ruff)
MYPY := $(if $(wildcard $(VENV_BIN)/mypy),$(VENV_BIN)/mypy,mypy)

dev:
	docker compose up --build postgres api

api:
	$(VENV_BIN)/uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload

frontend:
	npm --prefix frontend install
	npm --prefix frontend run dev

test:
	PYTHONDONTWRITEBYTECODE=1 $(PYTEST) $(path)

lint:
	PYTHONDONTWRITEBYTECODE=1 $(RUFF) check .
	PYTHONDONTWRITEBYTECODE=1 $(MYPY) backend tests
	npm --prefix frontend run build
