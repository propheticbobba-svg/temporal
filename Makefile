.PHONY: dev test lint frontend

VENV_BIN := .venv/bin
PYTEST := $(if $(wildcard $(VENV_BIN)/pytest),$(VENV_BIN)/pytest,pytest)
RUFF := $(if $(wildcard $(VENV_BIN)/ruff),$(VENV_BIN)/ruff,ruff)
MYPY := $(if $(wildcard $(VENV_BIN)/mypy),$(VENV_BIN)/mypy,mypy)

dev:
	docker compose up --build postgres api

frontend:
	npm --prefix frontend install
	npm --prefix frontend run dev

test:
	$(PYTEST) $(path)

lint:
	$(RUFF) check .
	$(MYPY) .
	npm --prefix frontend run build
