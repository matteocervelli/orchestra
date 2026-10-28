from __future__ import annotations

from copy import deepcopy

import pytest

CANONICAL = (
    "app-himalaia",
    "app-ratio",
    "adlimen-ui",
    "claude-dotfiles",
    "nexus",
    "atrium",
    "orchestra",
    "adlimen-cicd",
    "adlimen-infra",
    "adlimen-harness",
    "adlimen-auth",
    "limen-assistant",
)
ALIASES = {
    "himalaia": "app-himalaia",
    "ratio": "app-ratio",
    "adlimenui": "adlimen-ui",
    "dotfiles": "claude-dotfiles",
}


@pytest.mark.parametrize("canonical", CANONICAL)
@pytest.mark.parametrize(
    "qualified,dot", [(False, ""), (False, "."), (True, ""), (True, ".")]
)
def test_registered_authority_is_canonical_and_idempotent(canonical, qualified, dot):
    from orchestra.dashboard.common import repository_authority
    from orchestra.dashboard.repository import repository_key

    raw = ("matteocervelli/" if qualified else "") + canonical + dot
    assert repository_authority(canonical) == "matteocervelli/" + canonical
    assert repository_key(raw) == canonical
    assert repository_key(repository_key(raw)) == canonical


@pytest.mark.parametrize("alias,canonical", ALIASES.items())
@pytest.mark.parametrize("dot", ["", "."])
def test_only_bare_short_aliases_are_registered(alias, canonical, dot):
    from orchestra.dashboard.repository import repository_key

    assert repository_key(alias + dot) == canonical
    raw = "matteocervelli/" + alias + dot
    assert repository_key(raw) == raw


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "unknown.",
        "foreign/app-himalaia.",
        "Nexus.",
        "Ratio.",
        " himalaia ",
        "app-himalaia..",
        "ratio..",
        "matteocervelli/nexus..",
        "matteocervelli/unknown",
        "infra",
        "auth",
        "harness",
        "__proto__",
        "https://github.com/matteocervelli/app-himalaia",
        "a/b/nexus",
    ],
)
def test_unregistered_values_are_literal(raw):
    from orchestra.dashboard.repository import repository_key

    assert repository_key(raw) == raw


@pytest.mark.parametrize("raw", [1, True, [], {}])
def test_invalid_repository_type_has_fixed_error(raw):
    from orchestra.dashboard.repository import repository_key

    with pytest.raises(ValueError, match=r"^invalid_repository_type$"):
        repository_key(raw)


def test_preview_adapter_preserves_allowlist_and_all_other_fields():
    from orchestra.dashboard.repository import preview_item

    nested = {"ask": ["unchanged"]}
    item = {"id": "opaque-exact-ID", "repo": "ratio", "nested": nested}
    before = deepcopy(item)
    result = preview_item(item, {"app-ratio": object()})
    assert result == {**item, "repo": "app-ratio"}
    assert result is not item and result["nested"] is nested
    assert item == before
    for raw in (
        None,
        {},
        {"repo": []},
        {"repo": "nexus"},
        {"repo": "foreign/app-ratio"},
    ):
        assert preview_item(raw, {"app-ratio": object()}) is raw


@pytest.mark.parametrize("step", ["promote", "release"])
def test_only_existing_repo_intents_normalize_scope(step):
    from orchestra.dashboard.repository import normalize_action_scope

    assert normalize_action_scope(step, "repo:ratio") == "repo:app-ratio"
    assert (
        normalize_action_scope(step, "repo:matteocervelli/app-ratio.")
        == "repo:app-ratio"
    )
    assert normalize_action_scope(step, "item:ratio") == "item:ratio"
    assert (
        normalize_action_scope(step, "repo:foreign/app-ratio.")
        == "repo:foreign/app-ratio."
    )


@pytest.mark.parametrize(
    "step", ["start", "review", "fix", "merge", "release_prepare", "deploy", ""]
)
def test_unrelated_intents_and_shipping_snapshots_stay_literal(step):
    from orchestra.dashboard.repository import normalize_action_scope

    for scope in ("repo:ratio", "item:ratio", "release:ratio:1.2:sha"):
        assert normalize_action_scope(step, scope) == scope
