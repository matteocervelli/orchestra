#!/usr/bin/env python3
"""Explicit title-admission CLI; no runtime root is inferred."""

from orchestra.dashboard.notes import main

if __name__ == "__main__":
    raise SystemExit(main())
