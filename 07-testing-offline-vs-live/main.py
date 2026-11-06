"""Module 07: tests that need no network, and tests that prove the network still behaves.

  python main.py             run the offline suite, then the live suite, and require both to pass
  python main.py --record    refresh recorded.json from the real api.osv.dev first

recorded.json is what the offline tests replay (see replay.py). `--record` rebuilds it by
running module 06's own code against the live API for every sample lockfile and storing the
answers: advisory ids per package, and the advisory records (trimmed to the fields the code reads).

Run:  python main.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "..", "samples")
KEEP = ("id", "aliases", "summary", "severity", "database_specific", "affected", "withdrawn")


def load_server06():
    spec = importlib.util.spec_from_file_location("server06", os.path.join(HERE, "..", "06-the-mcp-wrapper", "main.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def record() -> None:
    s = load_server06()
    os.environ.pop("MINIDEP_OSV_URL", None)
    query: dict[str, list[str]] = {}
    vulns: dict[str, dict] = {}
    for lock in (os.path.join(SAMPLES, "requirements.txt"), os.path.join(SAMPLES, "npm", "package-lock.json")):
        packages, _, _ = s.parse_lockfile(lock)
        ids = s.advisory_ids(sorted(packages))
        for pkg, vids in ids.items():
            query[f"{pkg.ecosystem}|{pkg.name}|{pkg.version}"] = vids
            for vid in vids:
                full = s.http_json(f"{s.osv_base()}/v1/vulns/{vid}")
                vulns[vid] = {k: full[k] for k in KEEP if k in full}  # trimmed: no references or long details
    with open(os.path.join(HERE, "recorded.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"query": query, "vulns": vulns}, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"recorded {len(query)} packages, {len(vulns)} advisories")


def pytest(*args: str) -> int:
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args]
    print("$", " ".join(cmd[2:]))
    return subprocess.run(cmd, cwd=HERE).returncode


def main() -> None:
    if "--record" in sys.argv:
        record()
    # -m "not live": the marker registered in pytest.ini lets us choose.
    assert pytest("-m", "not live") == 0, "offline suite failed"
    assert pytest("-m", "live") == 0, "live suite failed (is api.osv.dev reachable?)"
    print("OK")


if __name__ == "__main__":
    main()
