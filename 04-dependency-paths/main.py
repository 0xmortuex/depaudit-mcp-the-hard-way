"""Module 04: "minimist is vulnerable" is not actionable. "mkdirp pulls it in" is.

A transitive vulnerability cannot be fixed by editing the vulnerable package's
version; you act on a DIRECT dependency. So for every vulnerable package we
want the chain  direct -> ... -> vulnerable.

The tool for that is breadth-first search from all direct packages at once,
remembering for each package which package we reached it from (its "parent").
Following parents back from any package gives its SHORTEST chain.

Why BFS and not "walk the tree": real graphs are not trees. They have diamonds
(two packages depend on the same library) and cycles (npm allows them), so we
need a `seen` set, and we want the shortest chain, not the first one we trip over.

Run:  python main.py
"""

from __future__ import annotations

import json
import os
from collections import deque
from typing import NamedTuple

HERE = os.path.dirname(os.path.abspath(__file__))


class Pkg(NamedTuple):
    name: str
    version: str

    def label(self) -> str:
        return f"{self.name} {self.version}"


Graph = dict[Pkg, set[Pkg]]


def parents_from_roots(direct: set[Pkg], edges: Graph) -> dict[Pkg, Pkg | None]:
    """Multi-source BFS. Result maps every reachable package to the package we came from
    (None for the direct packages themselves). Sorting makes the chosen path deterministic
    when several shortest paths exist."""
    parent: dict[Pkg, Pkg | None] = {p: None for p in sorted(direct)}
    queue = deque(parent)
    while queue:
        cur = queue.popleft()
        for nxt in sorted(edges.get(cur, ())):
            if nxt not in parent:  # `seen` and `parent` in one dict; this also stops cycles
                parent[nxt] = cur
                queue.append(nxt)
    return parent


def chain_to(parent: dict[Pkg, Pkg | None], target: Pkg) -> list[Pkg] | None:
    if target not in parent:
        return None  # not reachable from any direct dependency (optional/platform-specific?)
    chain = [target]
    while (p := parent[chain[-1]]) is not None:
        chain.append(p)
    return chain[::-1]


def show(chain: list[Pkg]) -> str:
    return " > ".join(p.label() for p in chain)


def npm_graph(lock_text: str) -> tuple[set[Pkg], Graph]:
    """The npm parser from module 01, trimmed to what this module needs."""
    packages = json.loads(lock_text)["packages"]
    nodes = {k: Pkg(v.get("name", k.rsplit("node_modules/", 1)[1]), v["version"])
             for k, v in packages.items() if k.startswith("node_modules/") and "version" in v and not v.get("link")}

    def resolve(base: str, dep: str) -> Pkg | None:
        while True:
            hit = nodes.get(f"{base}/node_modules/{dep}" if base else f"node_modules/{dep}")
            if hit or not base:
                return hit
            cut = base.rfind("/node_modules/")
            base = base[:cut] if cut >= 0 else ""

    direct: set[Pkg] = set()
    edges: Graph = {}
    for key, entry in packages.items():
        if key in nodes:
            for dep in entry.get("dependencies", {}):
                if (t := resolve(key, dep)):
                    edges.setdefault(nodes[key], set()).add(t)
        elif not key.startswith("node_modules/"):
            for f in ("dependencies", "devDependencies", "optionalDependencies"):
                for dep in entry.get(f, {}):
                    if (t := resolve(key, dep)):
                        direct.add(t)
    return direct, edges


def main() -> None:
    # 1. The real lockfile: lodash, mkdirp and @babel/core, 35 packages in all.
    with open(os.path.join(HERE, "..", "samples", "npm", "package-lock.json"), encoding="utf-8") as fh:
        direct, edges = npm_graph(fh.read())
    parent = parents_from_roots(direct, edges)
    path = chain_to(parent, Pkg("minimist", "0.0.8"))
    assert path is not None
    print("minimist is pulled in by:", show(path))
    assert show(path) == "mkdirp 0.5.1 > minimist 0.0.8"
    json5 = chain_to(parent, Pkg("json5", "0.5.1"))
    assert json5 is not None
    print("json5 is pulled in by:   ", show(json5))
    assert show(json5) == "@babel/core 7.0.0 > json5 0.5.1"
    assert chain_to(parent, Pkg("lodash", "4.17.15")) == [Pkg("lodash", "4.17.15")]  # direct: chain of one
    assert len(parent) == 35, "everything in this lockfile is reachable from the three direct dependencies"

    # 2. A diamond with a long and a short way to the same package: BFS picks the short one.
    a, b, c, d, x = (Pkg(n, "1") for n in "abcdx")
    diamond: Graph = {a: {b, d}, b: {c}, c: {x}, d: {x}}
    assert show(chain_to(parents_from_roots({a}, diamond), x) or []) == "a 1 > d 1 > x 1"

    # 3. A cycle does not loop forever, and an unreachable package has no chain.
    cyc: Graph = {a: {b}, b: {a, c}, c: {b}}
    p = parents_from_roots({a}, cyc)
    assert show(chain_to(p, c) or []) == "a 1 > b 1 > c 1"
    assert chain_to(p, x) is None

    # 4. Two direct dependencies reaching the same package: the first (sorted) wins; either is a valid answer.
    two: Graph = {a: {x}, b: {x}}
    assert show(chain_to(parents_from_roots({a, b}, two), x) or "") == "a 1 > x 1"
    print("OK")


if __name__ == "__main__":
    main()
