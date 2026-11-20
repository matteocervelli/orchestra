"""Restricted pure-Python YAML parsing, not package graph resolution."""

from __future__ import annotations

from typing import Any, cast

# PyYAML has no bundled typing; exact6.0.3 is pinned for SafeLoader semantics.
import yaml  # type: ignore[import-untyped]

from orchestra.security.profile import ProfileError, require

_ALLOWED_TAGS = {"tag:yaml.org,2002:" + name for name in ("str", "int", "bool", "null")}


def _events(raw: str, depth_limit: int, node_limit: int) -> None:
    depth, nodes, documents = 0, 0, 0
    for event in yaml.parse(raw, Loader=yaml.SafeLoader):
        require(
            getattr(event, "anchor", None) is None
            and getattr(event, "tag", None) is None,
            "unsupported_dependency_syntax",
        )
        if isinstance(event, yaml.events.DocumentStartEvent):
            documents += 1
            require(documents == 1, "unsupported_dependency_syntax")
        if isinstance(
            event, (yaml.events.MappingStartEvent, yaml.events.SequenceStartEvent)
        ):
            depth += 1
            require(depth <= depth_limit, "unsupported_dependency_syntax")
        if isinstance(
            event, (yaml.events.MappingEndEvent, yaml.events.SequenceEndEvent)
        ):
            depth -= 1
        if isinstance(
            event,
            (
                yaml.events.MappingStartEvent,
                yaml.events.SequenceStartEvent,
                yaml.events.ScalarEvent,
                yaml.events.AliasEvent,
            ),
        ):
            nodes += 1
            require(nodes <= node_limit, "unsupported_dependency_syntax")


def _validate_node(node: Any) -> None:
    if isinstance(node, yaml.nodes.MappingNode):
        seen: set[str] = set()
        for key, value in node.value:
            require(
                isinstance(key, yaml.nodes.ScalarNode)
                and key.tag == "tag:yaml.org,2002:str",
                "unsupported_dependency_syntax",
            )
            require(
                key.value != "<<" and key.value not in seen,
                "unsupported_dependency_syntax",
            )
            seen.add(key.value)
            _validate_node(value)
    elif isinstance(node, yaml.nodes.SequenceNode):
        for child in node.value:
            _validate_node(child)
    else:
        require(
            isinstance(node, yaml.nodes.ScalarNode) and node.tag in _ALLOWED_TAGS,
            "unsupported_dependency_syntax",
        )


def load_yaml(
    raw: bytes,
    *,
    byte_limit: int = 4194304,
    depth_limit: int = 32,
    node_limit: int = 100000,
) -> dict[str, Any]:
    require(
        type(raw) is bytes and len(raw) <= byte_limit, "unsupported_dependency_syntax"
    )
    require(
        type(byte_limit) is int
        and 0 < byte_limit <= 4194304
        and type(depth_limit) is int
        and 0 < depth_limit <= 32
        and type(node_limit) is int
        and 0 < node_limit <= 100000,
        "unsupported_dependency_syntax",
    )
    try:
        text = raw.decode("utf-8", errors="strict")
        _events(text, depth_limit, node_limit)
        root = yaml.compose(text, Loader=yaml.SafeLoader)
        require(
            isinstance(root, yaml.nodes.MappingNode), "unsupported_dependency_syntax"
        )
        _validate_node(root)
        result = yaml.load(text, Loader=yaml.SafeLoader)
        require(type(result) is dict, "unsupported_dependency_syntax")
        return cast(dict[str, Any], result)
    except ProfileError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError, yaml.YAMLError):
        raise ProfileError("unsupported_dependency_syntax") from None
