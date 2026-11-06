"""Module 06: put the pieces behind MCP.

The library part (parse -> batch query -> merge aliases -> dependency paths) is the
previous modules in one file. The new part is small on purpose: an MCP server is
just functions with good docstrings, plus ONE rule about errors.

  python main.py --serve   run the MCP server on stdio (what Claude Code launches)
  python main.py           demo: start ourselves with --serve, act as an MCP client,
                           list the tools, call them, and check what comes back

The rule about errors: with mcp 2.x a client only ever sees the message of a
`ToolError`. Any other exception becomes the useless "Error executing tool X".
So expected failures (no lockfile here, OSV unreachable) are converted at the tool
boundary into ToolError with a message that says what to do next.

Run:  python main.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import deque
from typing import Any, NamedTuple

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "..", "samples")


class Pkg(NamedTuple):
    ecosystem: str
    name: str
    version: str

    def label(self) -> str:
        return f"{self.name} {self.version}"


class AuditError(Exception):
    """An expected failure whose message is written for the agent."""


# --------------------------------------------------------------------- parsing (module 01)


def parse_lockfile(path: str) -> tuple[set[Pkg], set[Pkg], dict[Pkg, set[Pkg]]]:
    """-> (packages, direct, edges) for requirements.txt or package-lock.json."""
    base = os.path.basename(path)
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as e:
        raise AuditError(f"cannot read {path}: {e.strerror}") from e
    if base == "requirements.txt":
        pkgs = set()
        for line in re.sub(r"\\\r?\n", " ", text).splitlines():
            m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([A-Za-z0-9][A-Za-z0-9._+!-]*)", line.strip())
            if m:
                pkgs.add(Pkg("PyPI", re.sub(r"[-_.]+", "-", m.group(1)).lower(), m.group(2)))
        return pkgs, set(pkgs), {}
    if base == "package-lock.json":
        try:
            packages = json.loads(text)["packages"]
        except (json.JSONDecodeError, KeyError) as e:
            raise AuditError(f"{path} is not an npm lockfile v2/v3 (no 'packages' map): regenerate it with npm 7+") from e
        nodes = {k: Pkg("npm", v.get("name", k.rsplit("node_modules/", 1)[1]), v["version"])
                 for k, v in packages.items() if k.startswith("node_modules/") and "version" in v and not v.get("link")}

        def resolve(b: str, dep: str) -> Pkg | None:
            while True:
                hit = nodes.get(f"{b}/node_modules/{dep}" if b else f"node_modules/{dep}")
                if hit or not b:
                    return hit
                cut = b.rfind("/node_modules/")
                b = b[:cut] if cut >= 0 else ""

        direct: set[Pkg] = set()
        edges: dict[Pkg, set[Pkg]] = {}
        for k, v in packages.items():
            if k in nodes:
                edges.setdefault(nodes[k], set()).update(t for d in v.get("dependencies", {}) if (t := resolve(k, d)))
            elif not k.startswith("node_modules/"):
                for f in ("dependencies", "devDependencies", "optionalDependencies"):
                    direct.update(t for d in v.get(f, {}) if (t := resolve(k, d)))
        return set(nodes.values()), direct, edges
    raise AuditError(f"{base} is not supported by this tutorial server (requirements.txt, package-lock.json)")


def find_lockfiles(path: str) -> list[str]:
    path = os.path.abspath(path)
    if os.path.isfile(path):
        return [path]
    if not os.path.isdir(path):
        raise AuditError(f"{path} does not exist. Pass a project directory or a lockfile.")
    found = [os.path.join(path, f) for f in ("requirements.txt", "package-lock.json") if os.path.isfile(os.path.join(path, f))]
    if not found:
        raise AuditError(f"no requirements.txt or package-lock.json in {path}. Generate a lockfile first, e.g. `npm install --package-lock-only`.")
    return found


# --------------------------------------------------------------------- OSV (module 03, short form)


def osv_base() -> str:
    return os.environ.get("MINIDEP_OSV_URL", "https://api.osv.dev").rstrip("/")


def http_json(url: str, body: dict | None = None) -> Any:
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        hint = " It is rate limiting us; wait a minute and retry." if e.code == 429 else ""
        raise AuditError(f"{url} answered HTTP {e.code}.{hint}") from e
    except urllib.error.URLError as e:
        raise AuditError(f"could not reach {url}: {e.reason}. Check the internet connection.") from e


def advisory_ids(pkgs: list[Pkg], chunk: int = 500) -> dict[Pkg, list[str]]:
    """Module 03 in short form: chunks of 500, then follow page tokens until none are left."""
    out: dict[Pkg, list[str]] = {p: [] for p in pkgs}
    for start in range(0, len(pkgs), chunk):
        pending: list[tuple[Pkg, str | None]] = [(p, None) for p in pkgs[start : start + chunk]]
        while pending:
            queries = []
            for p, token in pending:
                q: dict[str, Any] = {"package": {"name": p.name, "ecosystem": p.ecosystem}, "version": p.version}
                if token:
                    q["page_token"] = token
                queries.append(q)
            results = http_json(f"{osv_base()}/v1/querybatch", {"queries": queries})["results"]
            nxt: list[tuple[Pkg, str | None]] = []
            for (p, _), res in zip(pending, results):
                out[p] += [v["id"] for v in res.get("vulns", [])]
                if res.get("next_page_token"):
                    nxt.append((p, res["next_page_token"]))
            pending = nxt
    return out


# --------------------------------------------------------------------- merging and ranking

ORDER = ["CRITICAL", "HIGH", "MODERATE", "LOW", "UNKNOWN"]


def merge_aliases(records: list[dict]) -> list[list[dict]]:
    """GHSA-x, PYSEC-y and CVE-z can all describe one problem. Group records that name each
    other (directly or through a chain of aliases): connected components of a small graph."""
    groups: list[tuple[set[str], list[dict]]] = []
    for r in records:
        names = {r["id"], *r.get("aliases", [])}
        merged = [g for g in groups if g[0] & names]
        groups = [g for g in groups if not g[0] & names]
        all_names, all_recs = set(names), [r]
        for g in merged:
            all_names |= g[0]
            all_recs += g[1]
        groups.append((all_names, all_recs))
    return [g[1] for g in groups]


def severity(group: list[dict]) -> str:
    labels = [(r.get("database_specific") or {}).get("severity", "UNKNOWN").upper().replace("MEDIUM", "MODERATE") for r in group]
    return min(labels, key=lambda s: ORDER.index(s) if s in ORDER else len(ORDER))


def vkey(version: str) -> tuple:
    """Module 05's ordering, shortened: numbers compare as numbers; a pre-release sorts before its release."""
    m = re.match(r"^v?(\d+(?:\.\d+)*)(.*)$", version)
    nums = [int(x) for x in m.group(1).split(".")] if m else [0]
    while len(nums) > 1 and nums[-1] == 0:
        nums.pop()
    return (tuple(nums), 0 if m and m.group(2) else 1)


def fixed_in(group: list[dict], pkg: Pkg) -> str | None:
    """Advisories often list one fix per release branch (0.2.4 AND 1.2.6 for minimist). The
    useful answer is the smallest fixed version ABOVE the installed one."""
    fixes = [e["fixed"] for r in group for a in r.get("affected", [])
             if a.get("package", {}).get("name") == pkg.name and a["package"].get("ecosystem") == pkg.ecosystem
             for rng in a.get("ranges", []) if rng["type"] in ("ECOSYSTEM", "SEMVER")
             for e in rng["events"] if "fixed" in e]
    above = [f for f in fixes if vkey(f) > vkey(pkg.version)]
    return min(above, key=vkey) if above else None


def chain(parent: dict[Pkg, Pkg | None], pkg: Pkg) -> str | None:
    if pkg not in parent:
        return None
    out = [pkg]
    while (p := parent[out[-1]]) is not None:
        out.append(p)
    return " > ".join(x.label() for x in reversed(out))


def scan(path: str) -> str:
    lines: list[str] = []
    for lock in find_lockfiles(path):
        packages, direct, edges = parse_lockfile(lock)
        parent: dict[Pkg, Pkg | None] = {p: None for p in sorted(direct)}
        queue = deque(parent)
        while queue:  # module 04
            cur = queue.popleft()
            for nxt in sorted(edges.get(cur, ())):
                if nxt not in parent:
                    parent[nxt] = cur
                    queue.append(nxt)
        ids = advisory_ids(sorted(packages))
        records: dict[str, dict] = {}
        for vid in {i for v in ids.values() for i in v}:
            records[vid] = http_json(f"{osv_base()}/v1/vulns/{vid}")
        lines.append(f"{os.path.basename(lock)}: {len(packages)} packages, {len(direct)} direct, {len(packages) - len(direct)} transitive")
        rows = []
        for pkg, vids in ids.items():
            for group in merge_aliases([records[v] for v in vids]):
                rows.append((ORDER.index(severity(group)) if severity(group) in ORDER else 4, pkg, group))
        rows.sort(key=lambda r: (r[0], r[1]))
        if not rows:
            lines.append("  no known vulnerabilities")
        for rank, pkg, group in rows:
            fx = fixed_in(group, pkg)
            lines.append(f"  {ORDER[rank]:<8} {pkg.label()} {group[0]['id']}: {group[0].get('summary', '')[:70]}"
                         + (f" (fixed in {fx})" if fx else ""))
            if pkg not in direct:
                lines.append(f"           via {chain(parent, pkg) or 'unknown path'}")
    return "\n".join(lines)


# --------------------------------------------------------------------- the MCP server

mcp = MCPServer(
    "minidep",
    instructions="Audit a project's lockfiles (requirements.txt, package-lock.json) for known vulnerabilities via OSV.dev.",
)


@mcp.tool()
def scan_project(path: str) -> str:
    """Scan a project directory (or one lockfile) for known vulnerabilities.

    Supports requirements.txt (== pins) and package-lock.json (v2/v3). Returns packages
    counts, then vulnerable packages worst first with the advisory, the fixed-in version,
    and for transitive ones the dependency chain that pulls them in. Read-only; needs
    internet access to api.osv.dev.
    """
    try:
        return scan(path)
    except AuditError as e:
        # The ONE rule: expected failures leave as ToolError, message intact.
        raise ToolError(str(e)) from e


async def demo() -> None:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(command=sys.executable, args=[os.path.abspath(__file__), "--serve"])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        init = await session.initialize()
        print("server:", init.server_info.name)
        tools = (await session.list_tools()).tools
        print("tools:", [t.name for t in tools], "| schema:", tools[0].input_schema["properties"])
        assert [t.name for t in tools] == ["scan_project"]

        res = await session.call_tool("scan_project", {"path": os.path.join(SAMPLES, "npm")})
        text = res.content[0].text
        print(text)
        assert not res.is_error
        assert "35 packages, 3 direct, 32 transitive" in text
        assert "lodash 4.17.15" in text and "via mkdirp 0.5.1 > minimist 0.0.8" in text

        res = await session.call_tool("scan_project", {"path": os.path.join(SAMPLES, "requirements.txt")})
        assert not res.is_error and "requests 2.19.1" in res.content[0].text

        res = await session.call_tool("scan_project", {"path": os.path.join(SAMPLES, "does-not-exist")})
        print("error the agent sees:", res.content[0].text)
        assert res.is_error and "does not exist. Pass a project directory" in res.content[0].text
    print("OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    if ap.parse_args().serve:
        mcp.run()  # stdout belongs to JSON-RPC: never print() in this mode
    else:
        asyncio.run(demo())
