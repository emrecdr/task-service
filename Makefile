.PHONY: clean clean-all

# Remove Python bytecode and tool caches from the project tree.
# Skips .venv so dependency bytecode doesn't have to regenerate.
clean:
	find . -path ./.venv -prune -o -type d -name '__pycache__' -exec rm -rf {} +
	find . -path ./.venv -prune -o -type f -name '*.py[cod]' -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	@echo "✓ python + tool caches cleaned"

# Everything clean does, plus coverage, build artifacts, and Hurl reports.
clean-all: clean
	rm -rf .coverage coverage.xml htmlcov
	rm -rf build dist *.egg-info
	find reports -mindepth 1 ! -name '.gitkeep' -delete 2>/dev/null || true
	@echo "✓ coverage, build, and report artifacts cleaned"
