# Git Workflow — Python / FastAPI

## Branch Creation Rules

### Always Branch from the Default Branch

**ALWAYS check out the default branch (usually `development` or `main`) before creating a new feature branch.**

```bash
# CORRECT
git checkout development
git pull
git checkout -b feature/<feature-name>

# WRONG — creates branch from another feature branch
# Currently on feature/add-notifications
git checkout -b feature/add-user-settings  # Pollutes PR with unrelated commits!
```

**Why this matters:**
- PRs should contain only the commits for that specific feature
- Creating branches from feature branches pollutes git history
- Reviewers cannot review PRs cleanly when they include unrelated commits

### Branch Naming

- `feature/<feature-name>` — New features
- `fix/<issue-description>` — Bug fixes
- `refactor/<scope>` — Code improvements
- `hotfix/<critical-fix>` — Production-critical fixes

---

## Conventional Commit Format

Use conventional commit format with a body and Co-Authored-By trailer:

```bash
git commit -m "$(cat <<'EOF'
<type>(<scope>): <subject>

<body>

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

### Commit Types

| Type | Description | Example |
|------|-------------|---------|
| `feat` | New feature | `feat: Implement photo upload endpoint` |
| `fix` | Bug fix | `fix: Correct validation error in webhook` |
| `test` | Adding tests | `test: Add integration tests for login` |
| `docs` | Documentation | `docs: Update MODULE.md with Session model` |
| `refactor` | Code refactoring | `refactor: Extract service to singleton` |
| `style` | Formatting (ruff format) | `style: Apply ruff formatting` |
| `chore` | Maintenance | `chore: Update dependencies` |

### Scope Examples

- Service names: `identity`, `licences`, `photos`, `agenda`
- `core` — Changes in core infrastructure
- `api` — API layer changes

### Subject Guidelines

- Use imperative mood ("Add feature" not "Added feature")
- No period at the end
- Keep under 50 characters
- Be specific (not "Fix bug" but "Fix validation error in LoginRequest")

### Body Guidelines

- Explain what and why, not how
- Reference relevant files and components
- Mention test coverage

### Example Commits

**Simple feature:**

```bash
git commit -m "$(cat <<'EOF'
feat(identity): Implement login endpoint

Creates Session model for token management.
Adds password validation with bcrypt.

Tests: test_login_success, test_login_invalid_credentials

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

**Bug fix:**

```bash
git commit -m "$(cat <<'EOF'
fix(identity): Correct session expiry calculation

Previous implementation used local time instead of UTC.
Now uses datetime.now(UTC) for consistency.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Pull Request Format

Use `gh` CLI for consistent PR creation:

```bash
gh pr create --title "<type>: <description>" --body "$(cat <<'EOF'
## Summary
- <bullet point 1>
- <bullet point 2>
- <bullet point 3>

## Changes
- **Models:** <new models or changes>
- **Endpoints:** <new endpoints>
- **Background Tasks:** <scheduled tasks>
- **External Services:** <integrations added>

## Tests
- <number> tests covering <areas>
- Mocked repositories and external services
- ~<percentage>% coverage

## Test Plan
- [ ] Quality gates pass: `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest tests/unit/ -x`
- [ ] Run `uv run pytest app/services/<service>/tests -v` — all tests pass
- [ ] Verify MODULE.md updated

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

### PR Title Format

- Use conventional commit format: `<type>: <description>`
- Keep under 70 characters

### PR Body Sections

| Section | Purpose |
|---------|---------|
| **Summary** | 3-5 bullet points explaining what was done |
| **Changes** | Organized by category (Models, Endpoints, Tasks, Services) |
| **Tests** | Test count, coverage, mocking strategy |
| **Test Plan** | Checklist for reviewers to verify the PR |

---

## Common Mistakes and Fixes

### Creating branches from feature branches

```bash
# WRONG — On feature/add-notifications
git checkout -b feature/add-user-settings

# FIX
git checkout development
git pull
git checkout -b feature/add-user-settings
```

### Committing without proper format

```bash
# WRONG
git commit -m "fixed bug"

# FIX — Use conventional commit with body
git commit -m "$(cat <<'EOF'
fix(identity): Correct session expiry calculation

Previous implementation used local time instead of UTC.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

### Pushing to wrong remote

```bash
# WRONG
git push  # May push to wrong branch

# FIX — Use explicit push with upstream
git push --set-upstream origin feature/<feature-name>
```

### Branch already exists

```bash
# Delete old branch and recreate from default branch
git checkout development
git branch -D feature/X
git checkout -b feature/X
```

### Branch is behind remote

```bash
git checkout development
git pull
git checkout feature/X
git rebase development
```

### Never Amend After Push

NEVER use `git commit --amend` on commits that have been pushed. Always create NEW commits.

**Why**: Amending rewrites history, causing force-push requirements. Force-pushing to shared branches destroys teammates' work.

**If you already pushed**: Create a new commit with the fix. Never amend + force-push.

### Never Commit to Protected Branches

NEVER commit directly to `main` or `development` (or whatever the project's default branch is).

**Why**: Protected branches require PRs. Direct commits bypass review and CI.

**Always**: Create a feature/fix branch first, then merge via PR.

---

## Version Bump — Keep Sources In Sync

When a PR introduces a change that justifies a new version, bump **every** version source the project uses in the same commit. Concrete files vary per project, but typically include:

- A dedicated `VERSION` file (devt promotes this pattern — single line, `X.Y.Z`).
- The changelog file (commonly `docs/API-CHANGELOG.md` or `CHANGELOG.md`).
- The package-manager manifest, if the stack has one (for Python projects this is usually `pyproject.toml`'s `[project] version`).
- Any code-level constant or runtime exposure that's hard-coded rather than derived.

All numeric values MUST match. CI pipeline guards typically reject main-bound merges where `VERSION` is not strictly greater than main's via `sort -V`. See [`./api-changelog.md`](./api-changelog.md) for the full rule.

**Common failure**: bumping only the changelog when merging into the integration branch, then having the integration → main PR rejected because `VERSION` (and any package manifest) is still at the old number.

---

## Quality Checklist

Before committing or creating PR:

- [ ] On correct base branch (default branch, not another feature branch)
- [ ] Quality gates pass (lint + typecheck + tests for your stack)
- [ ] Commit message follows conventional format
- [ ] PR title uses `<type>: <description>` format
- [ ] Changes are staged and reviewed
- [ ] MODULE.md updated if service changed
- [ ] If version was bumped: every version source the project uses (VERSION, changelog, package manifest, runtime constants) shows the same `X.Y.Z`
