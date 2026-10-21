from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "evals" / "synthetic" / "runtime-boundary.json"


def test_runtime_boundary_fixture_is_well_formed_and_matches_gitignore() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert len(payload["cases"]) >= 10
    assert {case["ignored"] for case in payload["cases"]} == {False, True}

    for case in payload["cases"]:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "check-ignore", "--no-index", "-q", case["path"]],
            check=False,
        )
        assert (result.returncode == 0) is case["ignored"], case
