.PHONY: help all install \
        clean clean-all port-check-kill \
        lint typecheck test test-unit test-integration test-contract \
        hurl-e2e schemathesis migrate migrate-check db-revision db-up db-down \
        run \
        docker-build compose-up compose-down compose-logs

# Defaults; override with `make APP_PORT=9000 <target>`.
APP_PORT ?= 8000
export APP_PORT
DOCKER_IMAGE := internal-task-service:dev
DOCKER_COMPOSE := docker compose -f docker/docker-compose.yaml
# The dev database is the compose ``postgres`` service plus an overlay publishing its port, so the
# image, healthcheck and volume have one definition rather than two that can drift apart. The
# credentials are not single-sourced — see DEV_DB_USER below.
DOCKER_COMPOSE_DEV := docker compose -f docker/docker-compose.yaml -f docker/docker-compose.dev.yaml -p task-service-dev
# 5432 is what the default DATABASE_URL expects; exported so the overlay can publish it.
DEV_DB_PORT ?= 5432
export DEV_DB_PORT
# Must match the credentials docker/docker-compose.yaml gives the postgres service.
DEV_DB_USER := taskservice
DEV_DB_URL := postgresql+asyncpg://$(DEV_DB_USER):$(DEV_DB_USER)@localhost:$(DEV_DB_PORT)/$(DEV_DB_USER)

# An overridden ``DEV_DB_PORT`` has to reach ``make run`` as well, or ``db-up DEV_DB_PORT=5433``
# migrates 5433 and then the app connects to whatever .env pins — which on a machine where 5432 is
# already taken means silently talking to someone else's database rather than failing. The test is
# for the *default* (``file`` is the origin of the ``?=`` above) rather than for the override forms:
# both ``make db-up DEV_DB_PORT=5433`` (``command line``) and ``DEV_DB_PORT=5433 make db-up``
# (``environment``) must fire, and README documents the second style for APP_PORT. A plain
# ``make run`` still takes DATABASE_URL from .env, so nobody pointing at a remote database is
# redirected.
ifneq ($(origin DEV_DB_PORT),file)
export DATABASE_URL := $(DEV_DB_URL)
endif

.DEFAULT_GOAL := help

help: ## ✨ Show this help message
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

# Pre-push gate: the CI checks that need nothing beyond a checkout and a Docker daemon — the pytest
# suite brings its own Postgres via testcontainers. Deliberately not a CI mirror. Gates wanting a
# reachable ``DATABASE_URL``, a built image, or a compose stack stay there, as does ``pip-audit``,
# whose verdict tracks the CVE feed rather than the diff — a new advisory *should* stop a deploy,
# not an unrelated push.
all: lint typecheck test schemathesis ## ✨ One-shot pre-push: static gates + full pytest + schemathesis

install: ## 📦 Sync dependencies and wire pre-commit hooks
	uv sync --all-groups
	uv run pre-commit install

# --- Code quality ----------------------------------------------------------

lint: ## 🧹 Ruff check + format + Bandit security scan + uv.lock freshness
	uv run ruff check app tests
	uv run ruff format --check app tests
	uv run bandit -c pyproject.toml -r app -q
	uv lock --check

typecheck: ## 🔍 pyright strict on app + tests
	uv run pyright

# --- Tests -----------------------------------------------------------------

test: ## 🧪 Run all tests with coverage gate (--cov-fail-under=80)
	uv run pytest

test-unit: ## 🧪 Unit tests only — feature-local, no FastAPI/DB
	uv run pytest app/services --no-cov

test-integration: ## 🧪 Integration tests — in-process FastAPI + Postgres (testcontainers)
	uv run pytest tests/integration --no-cov

test-contract: ## 🧪 Contract tests — repository ABC conformance
	uv run pytest tests/contract --no-cov

# --- Database migrations ---------------------------------------------------

migrate: ## 🗄️  Apply Alembic migrations (alembic upgrade head)
	uv run alembic upgrade head

migrate-check: migrate ## 🗄️  Drift gate: upgrade head + `alembic check` (models must match migrations). Needs a reachable DB.
	uv run alembic check

db-revision: ## 🗄️  Autogenerate a migration from model changes: make db-revision m="message"
	uv run alembic revision --autogenerate -m "$(m)"

# The compose Postgres publishes no ports (internal-only, for the container stack), so it cannot
# back ``make run``; the dev overlay adds a published port. Started idempotently, then migrated,
# because an empty schema is no more useful to ``make run`` than no database. The port pre-check
# runs only when our own container is absent, so a re-run of an already-started stack is a no-op
# rather than a conflict with itself — and it reports *which* container holds the port, which a
# raw bind failure from Docker would not.
db-up: ## 🗄️  Start a host-reachable dev Postgres on :$(DEV_DB_PORT) (idempotent) and apply migrations
	@if [ -z "$$($(DOCKER_COMPOSE_DEV) ps -q postgres 2>/dev/null)" ] && \
	    [ -n "$$(lsof -t -i TCP:$(DEV_DB_PORT) -sTCP:LISTEN 2>/dev/null)" ]; then \
	  echo "✗ port $(DEV_DB_PORT) is already in use — the default DATABASE_URL points there."; \
	  echo "  Free it, choose another port (make db-up DEV_DB_PORT=5433), or point DATABASE_URL at:"; \
	  docker ps --filter publish=$(DEV_DB_PORT) --format '    {{.Names}} ({{.Image}}) {{.Ports}}'; \
	  exit 1; \
	fi
	@$(DOCKER_COMPOSE_DEV) up -d --wait postgres
	@echo "✓ postgres ready on localhost:$(DEV_DB_PORT)"
	@DATABASE_URL=$(DEV_DB_URL) $(MAKE) migrate

# ``-v`` drops the named volume the stack declares for /var/lib/postgresql/data; without it the
# data would outlive the container and a later ``db-up`` would start on a stale schema.
db-down: ## 🛑 Remove the dev Postgres (``down -v`` — its data volume goes with it)
	@$(DOCKER_COMPOSE_DEV) down -v
	@echo "✓ dev postgres removed"

# --- E2E (against running container) ---------------------------------------

# ``--jobs 1``: the compose Postgres is shared across scenarios with no per-scenario
# reset, so parallel Hurl runs would race on task/list counts. (Postgres removed the
# old StaticPool single-connection constraint; concurrency *correctness* is covered by
# the advisory-lock tests under tests/integration.) ``down -v`` drops the volume so
# each run starts from a fresh, freshly-migrated database.
hurl-e2e: ## 🌐 Run Hurl E2E suite against the docker-compose stack (fresh DB per run)
	@trap '$(DOCKER_COMPOSE) down -v' EXIT; \
	$(DOCKER_COMPOSE) up -d --build --wait task-service && \
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
	rm -rf .pytest_cache .ruff_cache
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
