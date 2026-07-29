# Quality Gates — Python / FastAPI

> **About `parallel`**: gates tagged ``` ```bash parallel ``` are run concurrently
> by `scripts/run-quality-gates.sh`. Consecutive parallel-tagged blocks form one
> batch and finish when the slowest member finishes. Sequential blocks (no tag)
> run one at a time and force a flush of any pending parallel batch first.
> Use `parallel` only for read-only checks. Tools that mutate code (e.g.
> `ruff --fix`, `ruff format` without `--check`) belong in a fix-helper script,
> not a quality gate.

## Gate 1: Lint (read-only)

```bash parallel
uv run ruff check .
```

Catches lint errors. Read-only — does not modify files. Auto-fix is intentionally
NOT part of the gate (gates report, fix-helpers fix). Run `uv run ruff check --fix .`
manually when you want auto-fixes applied.

## Gate 2: Format check (read-only)

```bash parallel
uv run ruff format --check .
```

Asserts every file matches the formatter's expected output. Read-only.

## Gate 3: Type checking (read-only)

```bash parallel
uv run pyright
```

Type errors are blocking. Read-only. Alternative: `uv run pyright`.

## Gate 4: Unit tests

```bash
uv run pytest tests/unit/ -x
```

Runs unit tests, stops on first failure. Sequential — runs after the parallel
read-only batch above.

## Pass Criteria

- All gates must exit with code 0
- Any non-zero exit code = gate failure
- Run all gates before pushing code
- CI pipeline enforces these same gates on every PR

## Optional: Full Validation

For thorough pre-push validation including integration and E2E tests:

```bash
uv run pytest tests/ -x
```

## Fix Helpers (NOT gates)

These mutate code. Run manually, never as part of `/devt:quality`:

- `uv run ruff check --fix .` — apply auto-fixable lint suggestions
- `uv run ruff format .` — reformat files in place

> **ADR alignment gate**: before finishing, run `node bin/devt-tools.cjs memory affects <changed-file>` for each modified path and verify no governing ADR is contradicted. The architect agent enforces this; this gate documents the rule.
