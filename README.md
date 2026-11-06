# depaudit-mcp: The Hard Way

Build an MCP server that audits a project's dependencies, **transitive ones included**, by
reading its lockfiles and asking OSV.dev what is known to be broken. Start from raw lockfile
text and end with an agent that says: "`minimist 0.0.8` is critical, it comes in through
`mkdirp 0.5.1`, and upgrading to 0.2.4 fixes it."

At the end you will have built a small version of
[depaudit-mcp](https://github.com/0xmortuex/depaudit-mcp) yourself, and you will understand
the parts most "call a REST API from a tool" tutorials skip:

- **three lockfile formats** and why none of them can be treated as a flat list of names;
- **a real vulnerability database API**: batching, pagination, aliases, severity, fixed-in ranges;
- **graph search**, so "this package is vulnerable" becomes "this is the dependency to change";
- **honest failure**: rate limits and outages that say so instead of reporting a clean scan;
- **testing** code that depends on a service you do not control.

## Who This Is For

Developers who have built a hello-world MCP server and want a real one, and anyone curious how
`npm audit`, `pip-audit` and Dependabot get from a lockfile to a list of advisories.

**Prerequisites:** Python 3.11+ (for `tomllib`) and basic HTTP/JSON. Modules 02, 03, 05, 06 and 07
use the live `api.osv.dev`, PyPI and the npm registry, so you need internet access. No API keys.

```bash
pip install -r requirements.txt
python verify.py
```

## Modules

| # | Module | What You'll Build |
|---|--------|-------------------|
| 01 | [Lockfile Formats](01-lockfile-formats/) | Parsers for `requirements.txt`, `package-lock.json` (nested `node_modules`) and `uv.lock` into one data model |
| 02 | [The OSV API](02-the-osv-api/) | Query one package, read an advisory record, compute a CVSS score, find the fixed version |
| 03 | [Batching and Rate Limits](03-batching-and-rate-limits/) | `querybatch`, page tokens, concurrent record fetches, and 429 handling tested against a fake server |
| 04 | [Dependency Paths](04-dependency-paths/) | Multi-source breadth-first search: the shortest chain from a direct dependency to a vulnerable one |
| 05 | [Outdated Checks](05-outdated-checks/) | Version ordering, PyPI and npm "latest" lookups, major/minor/patch gaps |
| 06 | [The MCP Wrapper](06-the-mcp-wrapper/) | The pieces behind an MCP tool, merged aliases, severity order, and errors the agent can act on |
| 07 | [Testing Offline vs Live](07-testing-offline-vs-live/) | Recorded answers replayed over a real socket, fault injection, and a `live` pytest marker |

Each module contains:

- **`README.md`**: the concepts and design decisions
- **`main.py`**: a working, commented implementation that checks itself with `assert`
- **`break-it.md`**: challenges that break your own code, with hints

Module 07 additionally has `replay.py`, `test_scan.py` and `recorded.json`.

## How To Use This Course

**Option A: build along.** Read the modules in order, run each `main.py`, then do the break-it challenges.

**Option B: reference.** Each `main.py` stands alone (module 07 loads module 06 as the code under test).
`samples/` holds real lockfiles (`uv.lock` and `package-lock.json` written by the real tools) used by several modules.

## Every Module Is Verified

```bash
python verify.py          # all seven, for real
python verify.py 03 07    # some
```

## Architecture

```
 AI agent
    │  MCP over stdio                                  ← Module 06
    ▼
 scan_project(path)
    │  find lockfiles ─► parse ─► packages, direct set, edges      ← Module 01
    │                      │
    │                      ├─► OSV /v1/querybatch (+ pages)        ← Module 02, 03
    │                      ├─► OSV /v1/vulns/{id}, concurrently    ← Module 03
    │                      ├─► merge GHSA/PYSEC/CVE aliases        ← Module 06
    │                      └─► BFS from direct deps: "via a > b"   ← Module 04
    │  registries: PyPI / npm "latest" ─► major/minor/patch gap    ← Module 05
    ▼
 compact, severity-sorted text                       tests: replay + live   ← Module 07
```

## Key Design Principles

**1. A lockfile is a graph, not a list.** The vulnerable package is usually not one you chose. The
answer has to name the one you did.

**2. One problem, many records.** GHSA, PYSEC and CVE entries describe the same flaw. Count problems, not records.

**3. A failed check is not a clean check.** If OSV is unreachable or rate limiting, say so. Never return "no vulnerabilities".

**4. Errors are instructions.** "no lockfile found" is a dead end. "no lockfile found in X; run
`npm install --package-lock-only`" is the next step.

**5. Test against recordings, verify against reality.** Recorded answers make CI fast and deterministic. A scheduled live run notices when reality moved.

## Tech Stack

- **Language:** Python 3.11+
- **Network:** `urllib` and `concurrent.futures` from the standard library
- **Dependencies:** `mcp` (modules 06-07), `pytest` (module 07)

## License

MIT. Use it, modify it, ship it.

---

Built by [0xmortuex](https://github.com/0xmortuex)
