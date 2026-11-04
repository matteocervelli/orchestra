"""Pinned SOURCE acquisition and inert export boundaries; never provider calls."""

import ast
import json
from pathlib import Path

import pytest
from test_dashboard_semantic_export import FIXTURE, exporter, synthetic_donor


def test_selected_fixture_byte_and_ast_pins_are_enforced():
    import hashlib
    import json

    manifest = json.loads((FIXTURE / "manifest.json").read_text())
    actual_nodes = {}
    for path, digest in manifest["fixture_sha256"].items():
        raw = (FIXTURE / path).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest
        for node in ast.parse(raw).body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                actual_nodes[node.name] = exporter()._hash_node(node)
    for name, digest in manifest["selected_ast_sha256"].items():
        assert actual_nodes[name] == digest


def test_actual_selected_acquisition_fields_and_bodyless_late_row():
    from copy import deepcopy
    from types import SimpleNamespace

    from orchestra.dashboard.common import short_repo

    source = (FIXTURE / "acquisition.py.txt").read_text()
    namespace = {
        "C": SimpleNamespace(CACHE=Path("synthetic-cache")),
        "short_repo": short_repo,
        "is_proposal": lambda row: True,
    }
    exec(compile(source, "selected-static-acquisition", "exec"), namespace)
    calls = []
    first = {
        "repository": {"name": "nexus", "nameWithOwner": "matteocervelli/nexus"},
        "number": 207,
        "url": "https://github.com/matteocervelli/nexus/pull/207",
        "body": "## Summary\nPreserve package fields.",
    }

    def provider(args, *unused):
        calls.append(args)
        return [deepcopy(first)]

    probes = SimpleNamespace(
        gh_json=provider,
        pr_meta=lambda repo: {207: {"headRefName": "branch"}},
        release_facts=lambda repo: {
            "prs": [
                {
                    "number": 207,
                    "state": "MERGED",
                    "title": "merged",
                    "mergedAt": "2026-01-01",
                }
            ]
        },
    )
    acquired = [
        *namespace["fetch_prs"](probes),
        *namespace["fetch_proposals"](probes),
        *namespace["card_sources"](probes, ["nexus"]),
    ]
    assert len(calls) == 2
    for args in calls:
        fields = args[args.index("--json") + 1].split(",")
        assert {"body", "repository", "number", "url"} <= set(fields)
    assert acquired[0]["body"] == first["body"]
    assert "body" not in acquired[-1]
    deduped = list(
        {(row["repository"]["name"], row["number"]): row for row in acquired}.values()
    )
    assert deduped == [acquired[-1]]
    assert "body" not in deduped[0]
    from orchestra.dashboard.descriptions import recover_descriptions

    result = recover_descriptions(
        {"repo": "nexus", "pr": {"number": 207, "url": first["url"]}}, acquired
    )
    assert result["solution"] == "Preserve package fields."


def test_output_guard_rejects_undeclared_ast_or_byte_changes():
    module = exporter()
    original = (FIXTURE / "selected.py.txt").read_text()
    changed = module.adapt_workitems(original)
    expected = ast.parse(changed)
    module._verify_workitems(original, changed, expected)
    with pytest.raises(ValueError, match="output_ast"):
        module._verify_workitems(
            original, changed.replace("def identify(", "def unexpected("), expected
        )
    with pytest.raises(ValueError, match="output_bytes"):
        module._verify_workitems(original, changed + "# undeclared comment\n", expected)
    assert module._without_symbols(
        original, {"Ctx", "build", "finish"}
    ) == module._without_symbols(changed, {"Ctx", "build", "finish"})


def test_tokenizer_offset_preserves_non_linebreak_unicode_and_formfeed():
    module = exporter()
    source = (
        '"""Unicode \u2028 \x85 \x0c stays in its tokenizer line."""\nvalue = "é"\n'
    )
    node = ast.parse(source).body[1]
    after = module._splice(source, node.value, '"updated"')
    assert after == source.replace('value = "é"', 'value = "updated"')


def test_quality_requires_actual_severity_binding_before_output(tmp_path, monkeypatch):
    module, donor = synthetic_donor(tmp_path, monkeypatch)
    quality = donor / "bin/orchestra_dashboard/quality.py"
    source = quality.read_text().replace("    severity='warning'\n", "")
    pins = json.loads(module.PINS.read_text())
    pins["dependency_ast_sha256"]["quality.py"]["findings"] = module._hash_node(
        module._node(source, "findings")
    )
    module.PINS.write_text(json.dumps(pins))
    with pytest.raises(ValueError, match="severity_binding"):
        module.adapt_quality(source)
    assert not (tmp_path / "bundle").exists()


def test_acquisition_fixture_drift_rejects_without_fetch():
    module = exporter()
    pins = json.loads(module.PINS.read_text())
    pins["acquisition_fixture_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="acquisition_fixture"):
        module._check_acquisition(pins)


@pytest.mark.parametrize(
    "path", ["bin/wi_sources.py", "bin/wi_health.py", "bin/wi_release_links.py"]
)
@pytest.mark.parametrize("variant", ["current", "planned_r1"])
def test_production_vectors_bind_actual_acquisition_source_hashes(path, variant):
    pins = json.loads(exporter().PINS.read_text())
    evidence = {
        row["source"]: row["source_sha256"] for row in pins["acquisition_evidence"]
    }
    assert pins["before_vectors"][variant].get(path) == evidence[path]


@pytest.mark.parametrize(
    "path", ["bin/wi_sources.py", "bin/wi_health.py", "bin/wi_release_links.py"]
)
@pytest.mark.parametrize("variant", ["current", "planned_r1"])
def test_acquisition_source_drift_rejects_before_output(
    tmp_path, monkeypatch, path, variant
):
    module, donor = synthetic_donor(tmp_path, monkeypatch, variant)
    assert (donor / path).is_file()
    (donor / path).write_text("# changed provider source\n")
    output = tmp_path / "bundle"
    with pytest.raises(ValueError, match="donor_hash"):
        module.build_bundle(donor, output, variant)
    assert not output.exists()


def test_adapted_build_retains_acquisition_order_independently():
    module = exporter()
    output = module.adapt_workitems((FIXTURE / "selected.py.txt").read_text())
    build = next(
        n
        for n in ast.parse(output).body
        if isinstance(n, ast.FunctionDef) and n.name == "build"
    )
    assignments = {
        n.targets[0].id: (index, n)
        for index, n in enumerate(build.body)
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
    }
    index, acquired = assignments["acquired_prs"]
    dedupe_index, dedupe = assignments["all_prs"]
    assert dedupe_index == index + 1
    assert isinstance(acquired.value, ast.List)
    assert all(
        isinstance(element, ast.Starred) and isinstance(element.value, ast.Call)
        for element in acquired.value.elts
    )
    assert [ast.unparse(element.value.func) for element in acquired.value.elts] == [
        "fetch_prs",
        "H.fetch_proposals",
        "card_sources",
    ]
    names = [
        ast.unparse(node.func) for node in ast.walk(build) if isinstance(node, ast.Call)
    ]
    for name in ("fetch_prs", "H.fetch_proposals", "card_sources"):
        assert names.count(name) == 1
    comprehension = next(
        node for node in ast.walk(dedupe) if isinstance(node, ast.DictComp)
    )
    assert ast.unparse(comprehension.generators[0].iter) == "acquired_prs"
    assert ast.unparse(comprehension.key) == "(p['repository']['name'], p['number'])"


@pytest.mark.parametrize("merged_has_body", [False, True])
def test_canonical_app_ratio_merged_source_recovers_and_foreign_repo_rejects(
    merged_has_body,
):
    from types import SimpleNamespace

    from orchestra.dashboard.descriptions import recover_descriptions

    namespace = {}
    exec(
        compile(
            (FIXTURE / "acquisition.py.txt").read_text(), "selected-acquisition", "exec"
        ),
        namespace,
    )
    body = "## Summary\nSpecific authored package change."
    release_row = {"number": 42, "state": "MERGED", "title": "Specific change"}
    if merged_has_body:
        release_row["body"] = body
    probes = SimpleNamespace(release_facts=lambda repo: {"prs": [release_row]})
    merged = namespace["card_sources"](probes, ["app-ratio"])[0]
    assert merged["repository"] == {
        "name": "app-ratio",
        "nameWithOwner": "matteocervelli/app-ratio",
    }
    first = {**merged, "body": "## Summary\nSpecific authored package change."}
    if merged_has_body:
        assert merged["body"] == first["body"]
    item = {"repo": "ratio", "pr": {"number": 42, "url": merged["url"]}}
    assert (
        recover_descriptions(item, [first, merged])["solution"]
        == "Specific authored package change."
    )
    assert (
        recover_descriptions(item, [first, {**merged, "repo": "other/app-ratio"}])
        is None
    )


@pytest.mark.parametrize("variant", ["current", "planned_r1"])
def test_acquisition_evidence_cannot_be_omitted_from_before_vector(
    tmp_path, monkeypatch, variant
):
    module, donor = synthetic_donor(tmp_path, monkeypatch, variant)
    pins = json.loads(module.PINS.read_text())
    for vector in pins["before_vectors"].values():
        vector.pop("bin/wi_sources.py", None)
    module.PINS.write_text(json.dumps(pins))
    output = tmp_path / "bundle"
    with pytest.raises(ValueError, match="acquisition_vector"):
        module.build_bundle(donor, output, variant)
    assert not output.exists()
