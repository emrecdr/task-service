.PHONY: help all install \
        clean clean-all port-check-kill \
        lint typecheck test test-unit test-integration test-contract \
        hurl-e2e schemathesis \
        run \
        docker-build compose-up compose-down compose-logs

# Defaults; override with `make APP_PORT=9000 port-check-kill`.
APP_PORT ?= 8000
DOCKER_IMAGE := internal-task-service:dev
DOCKER_COMPOSE := docker compose -f docker/docker-compose.yaml

.DEFAULT_GOAL := help

help: ## ✨ Show this help message
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

all: lint typecheck test ## ✨ One-shot pre-push: static gates + full pytest suite

install: ## 📦 Sync dependencies and wire pre-commit hooks
	uv sync --all-groups
	uv run pre-commit install

# --- Code quality ----------------------------------------------------------

lint: ## 🧹 Ruff check + format + Bandit security scan
	uv run ruff check app tests
	uv run ruff format --check app tests
	uv run bandit -c pyproject.toml -r app -q

typecheck: ## 🔍 mypy strict on app + tests
	uv run mypy

# --- Tests -----------------------------------------------------------------

test: ## 🧪 Run all tests with coverage gate (--cov-fail-under=80)
	uv run pytest

test-unit: ## 🧪 Unit tests only — feature-local, no FastAPI/DB
	uv run pytest app/services --no-cov

test-integration: ## 🧪 Integration tests — in-process FastAPI + SQLite :memory:
	uv run pytest tests/integration --no-cov

test-contract: ## 🧪 Contract tests — repository ABC conformance
	uv run pytest tests/contract --no-cov

# --- E2E (against running container) ---------------------------------------

# ``--jobs 1`` is required: Phase 1's in-memory SQLite + StaticPool serialises
# on a single connection; Hurl's default parallel runs race on session state.
hurl-e2e: ## 🌐 Run Hurl E2E suite (--jobs 1) against the docker-compose service
	@trap '$(DOCKER_COMPOSE) down' EXIT; \
	$(DOCKER_COMPOSE) up -d --wait task-service && \
	hurl --test --jobs 1 \
	     --variable base_url=http://localhost:$(APP_PORT) \
	     --report-html reports/hurl/ \
	     --report-json reports/hurl/report.json \
	     tests/hurl/*.hurl

schemathesis: ## 🎲 Property-based OpenAPI tests via pytest (opt-in; ASGI in-process, no container needed)
	uv run pytest -m e2e --no-cov

# --- Local run -------------------------------------------------------------

# ``access-info`` prints the canonical URL set for any "the server is up" target.
# Pulled into one place so ``run`` and ``compose-up`` stay in sync.
define ACCESS_INFO
	@printf "\n\033[36m✓ Server reachable at http://localhost:$(APP_PORT)\033[0m\n"
	@printf "  • OpenAPI UI : \033[34mhttp://localhost:$(APP_PORT)/docs\033[0m\n"
	@printf "  • ReDoc      : \033[34mhttp://localhost:$(APP_PORT)/redoc\033[0m\n"
	@printf "  • Liveness   : \033[34mhttp://localhost:$(APP_PORT)/healthz\033[0m\n"
	@printf "  • Readiness  : \033[34mhttp://localhost:$(APP_PORT)/readyz\033[0m\n"
	@printf "  • Try it     : curl http://localhost:$(APP_PORT)/v1/tasks\n"
endef

run: port-check-kill ## 🚀 uvicorn --reload on $(APP_PORT)
	$(ACCESS_INFO)
	@printf "  • Stop       : Ctrl+C\n\n"
	uv run uvicorn app.main:app --host 0.0.0.0 --port $(APP_PORT) --reload

# --- Docker ----------------------------------------------------------------

docker-build: ## 🐳 Build the production image ($(DOCKER_IMAGE))
	docker build -f docker/Dockerfile -t $(DOCKER_IMAGE) .

compose-up: ## 🐳 Build (if changed) and start the container (detached, healthcheck-gated)
	$(DOCKER_COMPOSE) up -d --build --wait
	$(ACCESS_INFO)
	@printf "  • Logs       : make compose-logs\n"
	@printf "  • Stop       : make compose-down\n\n"

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
