.PHONY: dev test lint

VENV_BIN := .venv/bin
PYTEST := $(if $(wildcard $(VENV_BIN)/pytest),$(VENV_BIN)/pytest,pytest)
RUFF := $(if $(wildcard $(VENV_BIN)/ruff),$(VENV_BIN)/ruff,ruff)
MYPY := $(if $(wildcard $(VENV_BIN)/mypy),$(VENV_BIN)/mypy,mypy)

dev:
	docker compose up --build postgres redis api

test:
	$(PYTEST) $(path)

lint:
	$(RUFF) check .
	$(MYPY) .
