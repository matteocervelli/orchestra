# Conventions

- Python 3.12, strict type hints, immutable defaults, named exceptions.
- Standard library first; this extraction has no runtime package dependencies.
- Tests mirror source behavior under `tests/unit/` and use only synthetic data.
- Shell scripts use strict mode and receive their root through
  `ORCHESTRA_ROOT`; tests never point it at the live operational directory.
- Runtime artifacts are ignored and rejected if tracked.
