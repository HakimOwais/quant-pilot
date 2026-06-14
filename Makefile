.PHONY: help install dev fmt lint type test smoke audit up down logs migrate revision

PY   := python3.12
VENV := .venv
BIN  := $(VENV)/bin
COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env

help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## create venv and install package + dev deps
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e ".[dev]"

dev: ## run the API locally with autoreload
	$(BIN)/uvicorn quant_pilot.api.main:app --reload --host 127.0.0.1 --port 8000

fmt: ## auto-format and fix
	$(BIN)/ruff format src tests
	$(BIN)/ruff check --fix src tests

lint: ## lint + format check
	$(BIN)/ruff check src tests
	$(BIN)/ruff format --check src tests

type: ## type-check
	$(BIN)/mypy src

test: ## run all tests
	$(BIN)/pytest

smoke: ## run health smoke tests (no external deps needed)
	$(BIN)/pytest tests/test_health.py

audit: ## scan dependencies for known vulnerabilities
	$(BIN)/pip-audit

up: ## build + start the full stack (docker)
	$(COMPOSE) up -d --build

down: ## stop the stack
	$(COMPOSE) down

logs: ## tail stack logs
	$(COMPOSE) logs -f

migrate: ## apply DB migrations
	$(BIN)/alembic upgrade head

revision: ## autogenerate a migration:  make revision m="add users"
	$(BIN)/alembic revision --autogenerate -m "$(m)"
