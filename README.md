# Orchestra

Reusable, reviewable SDLC workflow sources for the Orchestra Nexus employee.
This repository contains code, tests, documentation, and synthetic evaluation
fixtures only. It is not Orchestra's runtime state store or scheduler.

## Repository flow

- Default branch: `main`.
- Integration branch: `auto/integration`.
- GitHub is the public fetch source and canonical issue tracker.
- Pushes go to both GitHub and Forgejo.
- Forgejo runs lint, type-check, security, and test jobs from
  `.forgejo/workflows/ci.yml`; GitHub is limited to review and communication
  workflows.
- There is no build, release, publish, or deploy workflow in this repository.

Changes are proposed to `auto/integration` on both forges. The initial source
extraction is tracked by
[`matteocervelli/nexus#184`](https://github.com/matteocervelli/nexus/issues/184).
It stays inactive until the P0 dispatch proof in `matteocervelli/nexus#64` is
merged and closed.

## Development

Python 3.12 and `uv` are required.

```bash
uv sync --frozen
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy --strict src
uv run pytest tests/unit -q
```

The shell launchers are source snapshots for tests and review. They do not
replace Nexus orchestration and are not connected to the live
`/data/dev/artifacts/orchestra` directory.

## Runtime boundary

Runtime state, logs, answers, task queues, pages, credentials, tokens, sessions,
and machine-local configuration must remain outside this repository. See
[`docs/architecture.md`](docs/architecture.md).
