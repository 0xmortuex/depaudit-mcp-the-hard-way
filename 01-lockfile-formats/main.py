"""Module 01: read lockfiles by hand.

Three formats, three parsers, one data model:

    requirements.txt     pinned lines, no graph at all
    package-lock.json    a flat map of install paths, with nested node_modules
    uv.lock              TOML: a [[package]] table per package, deps by name

Every parser returns a `Lock`: the set of locked packages, which of them the
project asked for directly, and the edges between them. Modules 03-06 only ever
see that shape, so supporting a new format later means writing one function.

Run:  python main.py        (needs Python 3.11+ for tomllib; no other packages)
"""

from __future__ import annotations

import json
import os
import re
import tomllib  # TOML parser in the standard library since Python 3.11
from dataclasses import dataclass, field
from typing import NamedTuple

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "..", "samples")


class Pkg(NamedTuple):
    """One locked package. A NamedTuple is hashable, so it can live in sets and be a dict key."""

    ecosystem: str  # the names OSV uses: "PyPI", "npm", ...
    name: str
    version: str

    def label(self) -> str:
        return f"{self.name} {self.version}"


@dataclass
class Lock:
    packages: set[Pkg] = field(default_factory=set)
    direct: set[Pkg] = field(default_factory=set)
    edges: dict[Pkg, set[Pkg]] = field(default_factory=dict)  # package -> what it depends on

    def add_edge(self, src: Pkg, dst: Pkg) -> None:
        self.edges.setdefault(src, set()).add(dst)


def pypi_name(name: str) -> str:
    """PEP 503: 'Flask_Login', 'flask.login' and 'flask-login' are the same project."""
    return re.sub(r"[-_.]+", "-", name).lower()


# --------------------------------------------------------------------- requirements.txt

# name, optional [extras], '==', version, optional '; marker'. Only exact pins are auditable:
# 'requests>=2' does not say which version is installed, so there is nothing to look up.
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*==\s*([A-Za-z0-9][A-Za-z0-9._+!-]*)\s*(?:;.*)?$")


def parse_requirements(text: str) -> Lock:
    lock = Lock()
    # Join "line \" continuations first (pip-compile writes --hash options that way).
    joined = re.sub(r"\\\r?\n", " ", text)
    for line in joined.splitlines():
        line = re.sub(r"\s#.*$", "", line).strip()  # strip trailing comments
        line = re.sub(r"\s--hash=\S+", "", line).strip()
        if not line or line.startswith(("#", "-")):  # blank, comment, or an option like -r / -e
            continue
        m = PIN.match(line)
        if m and "*" not in m.group(2):
            pkg = Pkg("PyPI", pypi_name(m.group(1)), m.group(2))
            lock.packages.add(pkg)
            lock.direct.add(pkg)  # a requirements file has no graph: every pin counts as direct
    return lock


# --------------------------------------------------------------------- package-lock.json


def parse_package_lock(text: str) -> Lock:
    data = json.loads(text)
    if data.get("lockfileVersion") not in (2, 3):
        raise ValueError("only npm lockfileVersion 2 and 3 have the flat 'packages' map")
    packages = data["packages"]
    lock = Lock()

    # Keys look like "node_modules/a/node_modules/b": b installed *inside* a, because a needs
    # a different version of b than the one hoisted to the top. The name is whatever follows
    # the last "node_modules/".
    nodes: dict[str, Pkg] = {}
    for key, entry in packages.items():
        if key.startswith("node_modules/") and "version" in entry and not entry.get("link"):
            pkg = Pkg("npm", entry.get("name", key.rsplit("node_modules/", 1)[1]), entry["version"])
            nodes[key] = pkg
            lock.packages.add(pkg)

    def resolve(base: str, dep: str) -> Pkg | None:
        """Node's algorithm: look in <base>/node_modules/<dep>, then in each parent directory."""
        while True:
            hit = nodes.get(f"{base}/node_modules/{dep}" if base else f"node_modules/{dep}")
            if hit:
                return hit
            if not base:
                return None
            cut = base.rfind("/node_modules/")
            base = base[:cut] if cut >= 0 else ""

    for key, entry in packages.items():
        if key in nodes:
            for dep in entry.get("dependencies", {}):
                target = resolve(key, dep)
                if target:
                    lock.add_edge(nodes[key], target)
        elif not key.startswith("node_modules/"):
            # "" is the project itself; other keys are workspace members. What they ask for is direct.
            for field_name in ("dependencies", "devDependencies", "optionalDependencies"):
                for dep in entry.get(field_name, {}):
                    target = resolve(key, dep)
                    if target:
                        lock.direct.add(target)
    return lock


# --------------------------------------------------------------------- uv.lock


def parse_uv_lock(text: str) -> Lock:
    data = tomllib.loads(text)
    lock = Lock()
    entries = data["package"]
    by_name: dict[str, list[Pkg]] = {}
    audited: dict[int, Pkg] = {}
    for i, e in enumerate(entries):
        # Only packages from a registry can be looked up in OSV. The project itself has
        # source = { virtual = "." } (or editable) and is the root of the graph instead.
        if "registry" in e.get("source", {}):
            pkg = Pkg("PyPI", pypi_name(e["name"]), e["version"])
            audited[i] = pkg
            by_name.setdefault(pkg.name, []).append(pkg)
            lock.packages.add(pkg)

    def resolve(dep: dict) -> Pkg | None:
        candidates = by_name.get(pypi_name(dep["name"]), [])
        if "version" in dep:  # uv adds a version when the same name is locked twice
            return next((c for c in candidates if c.version == dep["version"]), None)
        return candidates[0] if len(candidates) == 1 else None

    for i, e in enumerate(entries):
        if i in audited:
            for dep in e.get("dependencies", []):
                if (t := resolve(dep)):
                    lock.add_edge(audited[i], t)
        elif "virtual" in e.get("source", {}) or "editable" in e.get("source", {}):
            roots = list(e.get("dependencies", []))
            for group in (e.get("dev-dependencies") or {}).values():
                roots += group
            for dep in roots:
                if (t := resolve(dep)):
                    lock.direct.add(t)
    return lock


def read(*parts: str) -> str:
    with open(os.path.join(SAMPLES, *parts), encoding="utf-8") as fh:
        return fh.read()


def main() -> None:
    req = parse_requirements(read("requirements.txt"))
    print("requirements.txt:", sorted(p.label() for p in req.packages))
    # flask>=1.0 and numpy==1.* are not exact pins, so they are skipped.
    assert {p.label() for p in req.packages} == {"requests 2.19.1", "pyyaml 5.3", "jinja2 2.10"}
    assert req.direct == req.packages and not req.edges

    npm = parse_package_lock(read("npm", "package-lock.json"))
    print(f"package-lock.json: {len(npm.packages)} packages, {len(npm.direct)} direct")
    assert {p.label() for p in npm.direct} == {"lodash 4.17.15", "mkdirp 0.5.1", "@babel/core 7.0.0"}
    assert len(npm.packages) == 35
    mkdirp = Pkg("npm", "mkdirp", "0.5.1")
    assert Pkg("npm", "minimist", "0.0.8") in npm.edges[mkdirp]  # the transitive dependency we will audit

    uv = parse_uv_lock(read("uv", "uv.lock"))
    print(f"uv.lock: {len(uv.packages)} packages, direct = {sorted(p.label() for p in uv.direct)}")
    assert Pkg("PyPI", "requests", "2.19.1") in uv.direct
    assert Pkg("PyPI", "urllib3", "1.23") in uv.edges[Pkg("PyPI", "requests", "2.19.1")]
    assert not any(p.name == "demo" for p in uv.packages)  # the project is not one of its own dependencies

    # A nested node_modules: package "a" needs b@2, the hoisted b is 1.0.0.
    nested = parse_package_lock(json.dumps({
        "lockfileVersion": 3,
        "packages": {
            "": {"dependencies": {"a": "1"}},
            "node_modules/a": {"version": "1.0.0", "dependencies": {"b": "2"}},
            "node_modules/b": {"version": "1.0.0"},
            "node_modules/a/node_modules/b": {"version": "2.0.0"},
        },
    }))
    assert nested.edges[Pkg("npm", "a", "1.0.0")] == {Pkg("npm", "b", "2.0.0")}
    print("OK")


if __name__ == "__main__":
    main()
