.PHONY: help \
        clean clean-all port-check-kill \
        lint typecheck test test-unit test-integration test-contract quality \
        run \
        docker-build compose-up compose-down compose-logs

# Defaults; override with `make APP_PORT=9000 port-check-kill`.
APP_PORT ?= 8000
DOCKER_IMAGE := internal-task-service:dev
DOCKER_COMPOSE := docker compose -f docker/docker-compose.yaml

.DEFAULT_GOAL := help

help: ## ✨ Show this help message
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

# --- Code quality ----------------------------------------------------------

lint: ## 🧹 Ruff check + format + Bandit security scan
	uv run ruff check app tests
	uv run ruff format --check app tests
	uv run bandit -c pyproject.toml -r app -q

typecheck: ## 🔍 mypy strict on app + tests
	uv run mypy

quality: lint typecheck test ## ✨ Full quality pipeline (lint + typecheck + test with coverage)

# --- Tests -----------------------------------------------------------------

test: ## 🧪 Run all tests with coverage gate (--cov-fail-under=80)
	uv run pytest

test-unit: ## 🧪 Unit tests only — feature-local, no FastAPI/DB
	uv run pytest app/services --no-cov

test-integration: ## 🧪 Integration tests — in-process FastAPI + SQLite :memory:
	uv run pytest tests/integration --no-cov

test-contract: ## 🧪 Contract tests — repository ABC conformance
	uv run pytest tests/contract --no-cov

# --- Local run -------------------------------------------------------------

run: port-check-kill ## 🚀 uvicorn --reload on $(APP_PORT)
	uv run uvicorn app.main:app --host 0.0.0.0 --port $(APP_PORT) --reload

# --- Docker ----------------------------------------------------------------

docker-build: ## 🐳 Build the production image ($(DOCKER_IMAGE))
	docker build -f docker/Dockerfile -t $(DOCKER_IMAGE) .

compose-up: ## 🐳 Build (if changed) and start the container (detached)
	$(DOCKER_COMPOSE) up -d --build

compose-down: ## 🛑 Stop the container
	$(DOCKER_COMPOSE) down

compose-logs: ## 📜 Tail container logs (Ctrl+C to stop)
	$(DOCKER_COMPOSE) logs -f

# --- Cleanup ---------------------------------------------------------------

clean: ## 🧹 Remove Python bytecode and tool caches (preserves .venv)
	find . -path ./.venv -prune -o -type d -name '__pycache__' -exec rm -rf {} +
	find . -path ./.venv -prune -o -type f -name '*.py[cod]' -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	@echo "✓ python + tool caches cleaned"

clean-all: clean ## 💣 ``clean`` + coverage, build artifacts, Hurl reports
	rm -rf .coverage coverage.xml htmlcov
	rm -rf build dist *.egg-info
	find reports -mindepth 1 ! -name '.gitkeep' -delete 2>/dev/null || true
	@echo "✓ coverage, build, and report artifacts cleaned"

port-check-kill: ## 🚦 Free $(APP_PORT) — TERM then KILL the listener if any
	@if command -v lsof >/dev/null; then \
		PIDS=$$(lsof -t -i TCP:$(APP_PORT) -sTCP:LISTEN 2>/dev/null || true); \
		if [ -n "$$PIDS" ]; then \
			echo ">>> Port $(APP_PORT) is in use by PID(s): $$PIDS — sending TERM"; \
			kill -TERM $$PIDS || true; \
			sleep 1; \
			STILL=$$(lsof -t -i TCP:$(APP_PORT) -sTCP:LISTEN 2>/dev/null || true); \
			if [ -n "$$STILL" ]; then \
				echo ">>> Still alive: $$STILL — sending KILL"; \
				kill -9 $$STILL || true; \
			fi; \
			echo "✓ port $(APP_PORT) freed"; \
		else \
			echo "✓ port $(APP_PORT) already free"; \
		fi; \
	else \
		echo "warn: 'lsof' not found — cannot check $(APP_PORT)"; \
	fi
