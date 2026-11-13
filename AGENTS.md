# Repository Guidelines

## Scope

This repository contains reusable Orchestra workflow sources, tests,
documentation, and synthetic evaluation fixtures. Nexus owns orchestration,
policy, dispatch, capacity, cancellation, and exact resume. Atrium owns durable
application state. Do not add another scheduler or state authority here.

## Runtime boundary

Never commit live task files, queue or ledger data, logs, answers, pages,
credentials, tokens, sessions, local paths, or native runtime references. The
operational directory `/data/dev/artifacts/orchestra` remains separate and must
not be moved or mutated as part of repository work.

## Validation

Use Python 3.12 and the frozen lock:

```bash
uv sync --frozen
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy --strict src
uv run pytest tests/unit -q
```

CI executes only on Forgejo through `.forgejo/workflows/ci.yml`. GitHub
workflows, if added, may provide review or communication only. Do not add
automatic build, release, publish, or deploy jobs.

## Delivery

Work in a dedicated worktree based on `origin/auto/integration`. Open matching
GitHub and Forgejo pull requests to `auto/integration`. Never merge, tag,
release, or deploy from an implementation task.
