"""Pure prior-publication ownership; an explicit caller capability, never a reader."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from .common import repository_authority
from .provenance import qualified_pr
from .shadow_graph import ShadowBlocked


@dataclass(frozen=True)
class Artifact:
    name: str
    sha256_bytes: str
    byte_count: int


@dataclass(frozen=True)
class PriorOwner:
    id: str
    repo: str
    slugs: tuple[str, ...]
    pr_number: int | None = None
    pr_url: str | None = None


@dataclass(frozen=True)
class PriorBindingInput:
    generated: str
    board_digest: str
    artifacts: tuple[Artifact, ...]
    coverage: str
    owners: tuple[PriorOwner, ...]
    schema: str = "orchestra-prior-ownership/1"


@dataclass(frozen=True)
class PriorWitness:
    """Only the authorized caller constructs this, after independent verification."""

    prior: PriorBindingInput
    sha256: str
    verified_at: datetime


def generation(value: str) -> datetime:
    if (
        type(value) is not str
        or re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", value) is None
    ):
        raise ShadowBlocked("prior_invalid", "$prior.generation")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ShadowBlocked("prior_invalid", "$prior.generation") from None


def _hex(value: str) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _key(value: str, limit: int) -> bool:
    return (
        type(value) is str
        and len(value) <= limit
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value) is not None
    )


def _artifacts(prior: PriorBindingInput) -> None:
    if type(prior.artifacts) is not tuple or len(prior.artifacts) != 2:
        raise ShadowBlocked("prior_invalid", "$prior.scope")
    for item, name in zip(
        prior.artifacts, ("work-items.json", "work-items-archive.json"), strict=True
    ):
        if type(item) is not Artifact or item.name != name:
            raise ShadowBlocked("prior_invalid", "$prior.scope")
        if (
            not _hex(item.sha256_bytes)
            or type(item.byte_count) is not int
            or not 0 < item.byte_count <= 10 * 1024 * 1024
        ):
            raise ShadowBlocked("prior_invalid", "$prior.scope")


def _time_window(
    prior: PriorBindingInput, witness: PriorWitness, now: datetime, max_age: int
) -> None:
    if type(now) is not datetime or type(witness.verified_at) is not datetime:
        raise ShadowBlocked("prior_invalid", "$prior.generation")
    if now.tzinfo is not UTC or witness.verified_at.tzinfo is not UTC:
        raise ShadowBlocked("prior_invalid", "$prior.generation")
    previous = generation(prior.generated)
    if (
        not previous <= witness.verified_at < now
        or not 0 < (now - previous).total_seconds() <= max_age
    ):
        raise ShadowBlocked("prior_invalid", "$prior.generation")


def _admit(
    prior: PriorBindingInput, witness: PriorWitness, now: datetime, max_age: int
) -> None:
    if type(prior) is not PriorBindingInput or type(witness) is not PriorWitness:
        raise ShadowBlocked("prior_invalid", "$prior.witness")
    if witness.prior is not prior or not _hex(witness.sha256):
        raise ShadowBlocked("prior_invalid", "$prior.witness")
    if (
        prior.schema != "orchestra-prior-ownership/1"
        or prior.coverage != "live_and_terminal"
    ):
        raise ShadowBlocked("prior_invalid", "$prior.scope")
    if (
        type(max_age) is not int
        or not 1 <= max_age <= 604800
        or not _hex(prior.board_digest)
    ):
        raise ShadowBlocked("prior_invalid", "$prior.generation")
    _time_window(prior, witness, now, max_age)
    _artifacts(prior)


def _owner_reference(owner: PriorOwner) -> str:
    if type(owner.pr_number) is not int or type(owner.pr_url) is not str:
        raise ShadowBlocked("prior_invalid", "$prior.scope")
    authority = repository_authority(owner.repo)
    ref = qualified_pr({"number": owner.pr_number, "url": owner.pr_url}, owner.repo)
    if not authority or not ref or ref["url"] != owner.pr_url:
        raise ShadowBlocked("prior_invalid", "$prior.scope")
    return owner.pr_url


def _owner_keys(owner: PriorOwner) -> list[tuple[str, str]]:
    if type(owner) is not PriorOwner or not _key(owner.id, 64):
        raise ShadowBlocked("prior_invalid", "$prior.scope")
    if type(owner.slugs) is not tuple or any(
        not _key(slug, 200) for slug in owner.slugs
    ):
        raise ShadowBlocked("prior_invalid", "$prior.scope")
    keys = [("task", slug) for slug in owner.slugs]
    if owner.pr_number is None and owner.pr_url is None:
        return keys
    keys.append(("pr", _owner_reference(owner)))
    return keys


def _register_owner(
    owner: PriorOwner, registry: dict[tuple[str, str], str], counts: dict[str, int]
) -> None:
    for key in _owner_keys(owner):
        existing = registry.get(key)
        if existing is not None and existing != owner.id:
            raise ShadowBlocked("prior_invalid", "$prior.scope")
        if existing is None:
            counts[key[0]] += 1
        registry[key] = owner.id


def derive_prior_bindings(
    prior: PriorBindingInput | None,
    witness: PriorWitness | None,
    *,
    now: datetime,
    max_age: int,
) -> list[dict[str, str]]:
    if prior is None or witness is None:
        raise ShadowBlocked("prior_missing", "$prior.witness")
    _admit(prior, witness, now, max_age)
    if type(prior.owners) is not tuple or len(prior.owners) > 5000:
        raise ShadowBlocked("prior_invalid", "$prior.scope")
    registry: dict[tuple[str, str], str] = {}
    counts = {"task": 0, "pr": 0}
    for owner in prior.owners:
        _register_owner(owner, registry, counts)
    if counts["task"] > 20000 or counts["pr"] > 5000:
        raise ShadowBlocked("prior_invalid", "$prior.scope")
    return [
        {"kind": kind, "key": key, "owner": owner}
        for (kind, key), owner in registry.items()
    ]
