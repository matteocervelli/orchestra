# Conventions

- Python 3.12, strict type hints, immutable defaults, named exceptions.
- Standard library first. Security checkpoint A declares exact runtime parser
  dependencies packaging26.3 and PyYAML6.0.3, promoted from existing lock entries
  without version or unrelated transitive changes. These are parsing libraries,
  not installed native scanners or live activation. Pure SafeLoader is wrapped
  by explicit YAML bounds; no dependency resolver or candidate hook runs.
- Tests mirror source behavior under `tests/unit/` and use only synthetic data.
- Shell scripts use strict mode and receive their root through
  `ORCHESTRA_ROOT`; tests never point it at the live operational directory.
- Runtime artifacts are ignored and rejected if tracked.

- Dashboard helpers receive filesystem roots explicitly and accept only bounded
  JSON task metadata. Task/note origin is assigned by the reader; reports cannot
  claim trusted origin. Missing or conflicting proof remains conservative.
- Runtime donor provenance contains relative source paths and hashes only. Export
  produces a review artifact; a CLI flag does not authorize application. Core
  support helpers preserve existing refs/short_repo semantics.
