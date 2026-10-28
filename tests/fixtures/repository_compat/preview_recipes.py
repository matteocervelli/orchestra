"""Synthetic module retaining the reviewed normalizer function body only."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

Deps = Paths = object
R = S = SimpleNamespace()


def serve_status(deps):
    return {}


@dataclass(frozen=True)
class Repo:
    name: str
    gh: str

    @property
    def path(self):
        return Path("synthetic") / self.name

    @property
    def short(self):
        return self.name


REPOS = {
    name: Repo(name, "matteocervelli/" + name)
    for name in ("app-himalaia", "app-ratio", "adlimen-ui", "atrium")
}


def normalize_item(item: dict | None) -> dict | None:
    """Resolve only configured GitHub slugs; retain the recipe's canonical state key."""
    if item is None:
        return None
    key = item.get("repo")
    if isinstance(key, str):
        key = key.removesuffix(".")
    for repo in REPOS.values():
        if key in (repo.gh, repo.name):
            return item | {"repo": repo.name}
    return item


def new_entry(st: dict, item: str, it: dict, d: Deps, p: Paths, started: str) -> dict:
    repo = R.REPOS[it["repo"]]
    others = {
        "previews": {k: v for k, v in st["previews"].items() if k != item}
    }  # a stale error entry
    n = S.next_n(others, repo)
    ports = S.alloc_ports(others, serve_status(d), d.port_free)
    pr, ref = S.target_of(it)
    return {
        "item": item,
        "repo": repo.name,
        "pr": pr,
        "ref": ref,
        "expected_sha": it.get("sha") or "",
        "sha": "",
        "n": n,
        "worktree": str(repo.path / ".worktrees" / f"preview-{n}"),
        "project": f"orchprev-{repo.short}-{n}",
        "compose": str(p.dir(item) / "compose.yaml"),
        "ports": ports,
        "url": f"https://{R.HOST}:{ports['https']}{R.link_path(repo.name)}",
        "login": R.login_of(repo.name),
        "pids": {},
        "starter_pid": d.pid,
        "state": "starting",
        "step": "Preparo l'anteprima",
        "error": "",
        "started_at": started,
        "live_at": "",
    }
