# Architecture and ownership

Orchestra is a reusable SDLC workflow employee. This repository stores only
reviewable implementation assets: source, tests, documentation, and synthetic
evaluation fixtures.

## Ownership boundaries

- Atrium owns durable work-unit, session, run, question, approval, and artifact
  state.
- Nexus owns orchestration, policy, FIFO ordering, cancellation, exact resume,
  capacity, adapter selection, and dispatch.
- Orchestra defines workflow behavior and adapters but is not a second state
  authority or scheduler.
- GitHub owns the public backlog. Forgejo owns CI execution.

The extracted launch scripts document the legacy operational mechanism and make
it testable. They are not installed or activated by this repository. A live
cutover requires the P0 proof in `matteocervelli/nexus#64` and must demonstrate
that Nexus is the sole dispatch owner.

## Excluded data

The repository excludes live `STATE.md`, continuation notes, ledger rows, queue
files, tasks, logs, answers, pages, credentials, tokens, sessions, caches, and
other machine-local runtime artifacts. The guard test verifies both ignore rules
and tracked-file absence.
