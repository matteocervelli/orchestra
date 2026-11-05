"""Pinned publisher SOURCE body, exercised with synthetic inputs only."""

import ast
import re
from pathlib import Path

import pytest
from test_dashboard_runtime_export import exporter, synthetic_donors

from orchestra.dashboard.quality import (
    audit,
    bind_detail,
    board_digest,
    detail_matches_board,
    publication_generated,
)
from orchestra.dashboard.repository import repository_key

# SOURCE publisher body; pre-existing core instrumentation removed to exercise emitter.
# Donor SHA256: 304b641de96c34503c789289fe1151f8f6588bdeabc18d4639ef24f0f01e1675
RAW_PUBLISH = (
    'def publish(data: dict, out: Path | None=None) -> None:\n    """Pu'
    "blish the live board, terminal archive and complete per-card deta"
    'il artifacts."""\n    out = out or C.OUT\n    archive_out = out.wit'
    "h_name('work-items-archive.json')\n    detail_dir = out.parent / '"
    "work-items-detail'\n    items = [item for item in data.get('items'"
    ", []) if isinstance(item, dict)]\n    ledger = [row for row in dat"
    "a.get('ledger', []) if isinstance(row, dict)]\n    live = [item fo"
    "r item in items if item.get('status') not in TERMINAL_STATUSES]\n "
    "   terminal = [item for item in items if item.get('status') in TE"
    "RMINAL_STATUSES]\n    recent_slugs = {child.get('slug') for item i"
    "n live for child in (item.get('children') or [])[-PUBLIC_LIST_LIM"
    "IT:] if isinstance(child, dict) and isinstance(child.get('slug'),"
    " str)}\n    public_children = [_compact_fields(child, required={'s"
    "lug'}) for child in data.get('children', []) if isinstance(child,"
    " dict) and (child.get('slug') in recent_slugs or child.get('runni"
    "ng') is True)]\n    public = {key: data[key] for key in ('generate"
    "d', 'statuses', 'decisions', 'host') if key in data}\n    public['"
    "items'] = [_public_item(item, ledger) for item in live]\n    publi"
    "c['children'] = public_children\n    terminal_slugs = {slug for it"
    "em in terminal for slug in item.get('slugs', []) if isinstance(sl"
    "ug, str)}\n    archive = dict(data)\n    archive['items'] = termina"
    "l\n    archive['children'] = [child for child in data.get('childre"
    "n', []) if isinstance(child, dict) and child.get('slug') in termi"
    "nal_slugs]\n    detail_dir.mkdir(parents=True, exist_ok=True)\n    "
    "for item in items:\n        item_id = item.get('id')\n        if no"
    "t isinstance(item_id, str) or not _SAFE_ITEM_ID.fullmatch(item_id"
    "):\n            raise ValueError(f'unsafe work item id: {item_id!r"
    "}')\n        _write_compact(_detail_item(item, ledger), detail_dir"
    " / f'{item_id}.json')\n    _write_compact(archive, archive_out)\n  "
    "  _write_compact(quality_audit({**data, 'items': live}), out.with"
    "_name('work-items-quality.json'))\n    _write_compact(public, out)"
)

RAW_MAIN = (
    "def main() -> None:\n    data = build()\n    errs = validate(data) "
    "+ duplicate_gaps(data)\n    if '--check' in sys.argv:\n        qual"
    "ity = quality_audit(data)\n        errs += [f\"{item['id']}: {issue"
    "['code']}: {issue['message']}\" for item in quality['items'] if it"
    "em['your_call'] for issue in item['issues'] if issue['severity'] "
    "== 'error']\n        for e in errs:\n            print('ERROR', e)\n"
    "        for it in data['items']:\n            fallback = [a for a "
    "in it['ask'] if a['rec'] == NO_REC]\n            if it['auto'] or "
    "fallback:\n                print('GAP', it['id'], it['status'], ',"
    "'.join(it['auto']), 'rec' if fallback else '')\n        todo = unc"
    "urated_open(data)\n        for it in todo:\n            print('ERRO"
    "R', it['id'], 'open item without title_it (fallback title)')\n    "
    "    gaps = step_gaps(data)\n        for g in gaps:\n            pri"
    "nt('ERROR', g)\n        raise SystemExit(1 if errs or todo or gaps"
    " else 0)\n    for e in errs:\n        print('workitems: contract vi"
    "olation:', e, file=sys.stderr)\n    publish(data)"
)


def publisher(tmp_path):
    root = tmp_path / "synthetic-donor"
    synthetic_donors(root)
    module = exporter()
    text = (root / "bin/workitems.py").read_text()
    text = module.replace_symbols(text, {"publish": RAW_PUBLISH})
    emitted = module._workitems(text)
    writes, seen, audits, events = {}, [], [], []

    def public_item(item, ledger):
        seen.append(item)
        return {
            key: value
            for key, value in item.items()
            if key
            in {
                "id",
                "repo",
                "title",
                "status",
                "your_call",
                "pr",
                "ask",
                "steps",
                "flags",
            }
        }

    def write(value, path):
        events.append(path.name)
        writes[path.name] = value

    def quality(data):
        events.append("audit")
        audits.append(data)
        return audit(data)

    namespace = {
        "Path": Path,
        "TERMINAL_STATUSES": {"Done"},
        "PUBLIC_LIST_LIMIT": 4,
        "_SAFE_ITEM_ID": re.compile(r"[a-z0-9-]+"),
        "read_json": lambda *args: {},
        "publication_generated": publication_generated,
        "board_digest": board_digest,
        "bind_detail": bind_detail,
        "_ledger_for": lambda item, ledger: ledger,
        "_public_item": public_item,
        "_compact_fields": lambda child, **kw: child,
        "_write_compact": write,
        "quality_audit": quality,
        "repository_key": repository_key,
    }
    functions = [
        n
        for n in ast.parse(emitted).body
        if isinstance(n, ast.FunctionDef) and n.name in {"publish", "_detail_item"}
    ]
    exec(
        compile(
            ast.Module(functions, type_ignores=[]), "synthetic-publisher.py", "exec"
        ),
        namespace,
    )
    return namespace["publish"], writes, seen, audits, events


class NoNestedRead:
    def __deepcopy__(self, memo):
        raise AssertionError("nested copy")

    def __eq__(self, other):
        raise AssertionError("nested compare")


def test_real_publish_projects_board_detail_archive_and_raw_audit_once(tmp_path):
    publish, writes, seen, audits, events = publisher(tmp_path)
    repos = (
        ["app-himalaia"] * 9
        + ["himalaia"] * 3
        + [
            "app-himalaia.",
            "nexus.",
            "ratio.",
            "app-ratio.",
            "matteocervelli/app-himalaia.",
            "app-himalaia..",
            "unknown.",
            "foreign/app-himalaia.",
            "matteocervelli/himalaia",
            "Nexus.",
            "Ratio.",
            " himalaia",
            None,
        ]
    )
    payload = NoNestedRead()
    items = [
        {
            "id": f"card-{i}",
            "repo": repo,
            "title": "Verificare contratto fonte",
            "status": "PR review",
            "your_call": i < 12,
            "ask": [{"id": "independent", "question": "Procedere?"}],
            "steps": {"check": {"state": "open"}},
            "flags": {"pin": True},
            "children": [{"slug": "synthetic", "repo": "himalaia"}],
            "repos": ["himalaia", "nexus."],
            "private_payload": payload,
        }
        for i, repo in enumerate(repos)
    ]
    items += [
        {"id": "missing", "status": "Plan"},
        {"id": "terminal", "repo": "himalaia", "status": "Done"},
    ]
    before = [dict(item) for item in items]
    data = {"generated": "synthetic-old", "items": items, "children": [], "ledger": []}
    publish(data, tmp_path / "work-items.json")
    board = writes["work-items.json"]
    assert len(board["items"]) == len(items) - 1
    assert (
        sum(
            bool(i.get("your_call"))
            for i in board["items"]
            if i.get("repo") == "app-himalaia"
        )
        == 12
    )
    assert [i["id"] for i in board["items"]] == [i["id"] for i in items[:-1]]
    assert len(audits) == 1 and all(
        a is b for a, b in zip(audits[0]["items"], items[:-1], strict=True)
    )
    assert events[-4:] == [
        "work-items-archive.json",
        "audit",
        "work-items-quality.json",
        "work-items.json",
    ]
    archive = writes["work-items-archive.json"]["items"]
    assert [i["id"] for i in archive] == ["terminal"] and archive[0][
        "repo"
    ] == "app-himalaia"
    assert board["generated"] != "synthetic-old"
    for original, saved in zip(items, before, strict=True):
        assert original.keys() == saved.keys()
        assert all(original[k] is saved[k] for k in saved)
        detail = writes[original["id"] + ".json"]
        assert detail.get("repo") == repository_key(original.get("repo"))
        assert ("repo" in detail) == ("repo" in original)
        assert detail_matches_board(detail, board, original["id"])
        for key in original.keys() - {"repo"}:
            assert detail[key] is original[key]
    for projected, original in zip(seen, items[:-1], strict=True):
        assert projected is not original
        assert all(projected[k] is original[k] for k in original.keys() - {"repo"})


def test_invalid_repository_fails_before_publication(tmp_path):
    publish, writes, _, _, _ = publisher(tmp_path)
    with pytest.raises(ValueError, match=r"^invalid_repository_type$"):
        publish(
            {"items": [{"id": "invalid", "repo": 17}]}, tmp_path / "work-items.json"
        )
    assert writes == {}


def test_pinned_publisher_source_and_main_check_use_same_raw_audit(tmp_path, capsys):
    import hashlib
    import json
    from types import SimpleNamespace

    from orchestra.dashboard.quality import main as standalone

    ast_digest = hashlib.sha256(
        ast.dump(ast.parse(RAW_PUBLISH), include_attributes=False).encode()
    ).hexdigest()
    assert (
        ast_digest == "e94eb2179a2e48596ae075c88a8fa92dff22b55a36195de8cf7634cc5f98a5fc"
    )
    donor = tmp_path / "source-fixture"
    synthetic_donors(donor)
    module = exporter()
    source = (
        module.replace_symbols(
            (donor / "bin/workitems.py").read_text(), {"publish": RAW_PUBLISH}
        )
        + "\n"
        + RAW_MAIN
    )
    emitted = module._workitems(source)
    before, after = module._function(source, "main"), module._function(emitted, "main")
    assert ast.dump(before) == ast.dump(after)
    item = {
        "id": "raw-dotted",
        "repo": "nexus.",
        "title": "Rivedere contratto",
        "status": "PR review",
        "your_call": False,
        "ask": [],
        "auto": [],
        "pr": {
            "number": 207,
            "url": "https://github.com/matteocervelli/nexus/pull/207",
        },
    }
    raw = {"items": [item]}
    calls = []

    def quality(data):
        assert data is raw
        calls.append(audit(data))
        return calls[-1]

    namespace = {
        "build": lambda: raw,
        "validate": lambda data: [],
        "duplicate_gaps": lambda data: [],
        "uncurated_open": lambda data: [],
        "step_gaps": lambda data: [],
        "quality_audit": quality,
        "sys": SimpleNamespace(argv=["workitems", "--check"]),
        "NO_REC": "none",
    }
    exec(
        compile(ast.Module([after], type_ignores=[]), "synthetic-main.py", "exec"),
        namespace,
    )
    with pytest.raises(SystemExit) as caught:
        namespace["main"]()
    assert caught.value.code == 0 and len(calls) == 1
    board = tmp_path / "raw.json"
    board.write_text(json.dumps(raw))
    assert standalone([str(board), "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == calls[0] == audit(raw)
    assert item["repo"] == "nexus."
