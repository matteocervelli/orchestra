# Orchestra repository and CI — issue 184

Status: approved by Matteo on 2026-10-16; option A (dedicated repository).

## Scope

Create `matteocervelli/orchestra` on GitHub and Forgejo, configure the standard
dual-push flow, and seed only reviewable source, tests, documentation, and
synthetic evaluation fixtures extracted from the operational Orchestra tree.
The live tree remains unchanged.

## Requirements

- REQ-01: GitHub and Forgejo repositories exist; `main` is documented as the
  default branch, GitHub is the fetch URL, and pushes target both forges.
- REQ-02: `.forgejo/workflows/ci.yml` calls `adlimen-cicd` reusable workflows
  pinned to `v3.6.0` and covers format/lint, strict type-check, security, and
  tests on pull requests to `auto/integration`.
- REQ-03: No automatic deploy, release, publish, or build workflow exists;
  GitHub workflows are absent or review/communication-only.
- REQ-04: `.gitignore` excludes runtime state, local artifacts, credentials,
  tokens, sessions, and caches. A guard test fails if excluded runtime files are
  trackable or tracked.
- REQ-05: The seed contains only the authorized launcher/autospawn, Slack API,
  Slack thread, and ledger reconciliation source plus tests, docs, and synthetic
  fixtures. It contains no copied live tasks, state, ledger, logs, answers,
  pages, tokens, or sessions.
- REQ-06: Because `nexus#64` remains open and PR #191 is draft, the extracted
  launchers remain inert. This change does not install, activate, or connect
  them to `/data/dev/artifacts/orchestra`.

## Approved decisions

- Dedicated repository, not a Nexus module and not a migration of the runtime
  directory.
- Python 3.12 with `uv`; no new runtime dependency.
- GitHub remains the canonical issue tracker; Forgejo runs CI.
- Pull requests target `auto/integration` on both forges.
- The generic `ci-setup` lib-py topology (separate push, publish, and release callers) is
  intentionally not applied: issue 184 requires one `ci.yml` and explicitly
  forbids automatic deploy/release/publish. The single caller still delegates
  PR quality and tests to `adlimen-cicd@v3.6.0`. PR-only execution also avoids
  duplicate push/PR runs for the same review SHA.

## File manifest

- `.env.example`
- `.forgejo/workflows/ci.yml`
- `.gitignore`
- `.python-version`
- `AGENTS.md`
- `CHANGELOG.md`
- `README.md`
- `pyproject.toml`
- `uv.lock`
- `docs/architecture.md`
- `docs/codebase/architecture.md`
- `docs/development/dependencies.md`
- `docs/codebase/INDEX.md`
- `docs/codebase/conventions.md`
- `docs/codebase/test.md`
- `docs/specs/2026-10-20-orchestra-repository-issue-184.md`
- `evals/synthetic/runtime-boundary.json`
- `scripts/autospawn.sh`
- `scripts/spawn.sh`
- `src/orchestra/__init__.py`
- `src/orchestra/ledger_sync.py`
- `src/orchestra/slack_api.py`
- `src/orchestra/slack_thread.py`
- `tests/unit/test_launchers.py`
- `tests/unit/test_ledger_sync.py`
- `tests/unit/test_repository_boundary.py`
- `tests/unit/test_slack_api.py`
- `tests/unit/test_slack_thread.py`
- `tests/unit/test_synthetic_evals.py`

## Validation

- `uv lock --check`
- `uv run ruff format --check src tests`
- `uv run ruff check src tests`
- `uv run mypy --strict src`
- `uv run pytest tests/unit -q --cov=src --cov-fail-under=80`
- shell syntax checks for `scripts/*.sh`
- `security-verify scan`
- Forgejo exact-head CI on the pull request branch
