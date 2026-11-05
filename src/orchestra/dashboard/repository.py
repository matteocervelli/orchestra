"""Pure repository keys shared by presentation and contained runtime adapters."""

from __future__ import annotations

from collections.abc import Container
from typing import Any

from .common import repository_authority


def repository_key(value: str | None) -> str | None:
    """Resolve existing authority only; preserve unregistered literal values."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid_repository_type")
    authority = repository_authority(value.removesuffix("."))
    return authority.split("/", 1)[1] if authority else value


def preview_item(
    item: dict[str, Any] | None, recipes: Container[str]
) -> dict[str, Any] | None:
    """Normalize a copied item only when its recipe is already configured."""
    if item is None or not isinstance(item.get("repo"), str):
        return item
    key = repository_key(item["repo"])
    return item | {"repo": key} if key is not None and key in recipes else item


def normalize_action_scope(step: str, scope: str) -> str:
    """Compare only existing repository intents; leave item/shipping scopes exact."""
    if step in ("promote", "release") and scope.startswith("repo:"):
        return "repo:" + str(repository_key(scope[5:]))
    return scope
