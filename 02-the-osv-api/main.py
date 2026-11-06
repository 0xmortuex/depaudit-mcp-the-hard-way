"""Module 02: ask OSV.dev about one package, then read the answer.

Uses only the standard library and the REAL api.osv.dev (no key needed).

    POST /v1/query      one package version -> full advisory records
    POST /v1/querybatch many package versions -> only advisory IDs  (module 03)
    GET  /v1/vulns/{id} one advisory record

We look up requests 2.19.1, a version with a well-known flaw (CVE-2018-18074:
the Authorization header is leaked on an https -> http redirect), and pull out
what a report needs: id, summary, severity, and the version that fixes it.

Run:  python main.py
"""

from __future__ import annotations

import json
import math
import urllib.request
from typing import Any

OSV = "https://api.osv.dev"


def post(url: str, body: dict) -> Any:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def get(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.loads(resp.read())


# --------------------------------------------------------------------- severity

# CVSS v3 base score, from the vector string OSV gives us, e.g.
#   CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N
# The formula is in the FIRST.org specification (section 7.1). Each metric maps to a weight.
AV = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}  # attack vector: network ... physical
AC = {"L": 0.77, "H": 0.44}  # attack complexity
UI = {"N": 0.85, "R": 0.62}  # user interaction
CIA = {"H": 0.56, "L": 0.22, "N": 0.0}  # confidentiality / integrity / availability impact


def roundup(x: float) -> float:
    """Round UP to one decimal, the way the spec defines it (avoiding float noise)."""
    i = round(x * 100000)
    return i / 100000.0 if i % 10000 == 0 else (math.floor(i / 10000) + 1) / 10.0


def cvss3_score(vector: str) -> float:
    m = dict(part.split(":") for part in vector.split("/")[1:])
    changed = m["S"] == "C"  # does the attack escape the vulnerable component's own scope?
    pr = {"N": 0.85, "L": 0.68 if changed else 0.62, "H": 0.5 if changed else 0.27}[m["PR"]]
    iss = 1 - (1 - CIA[m["C"]]) * (1 - CIA[m["I"]]) * (1 - CIA[m["A"]])
    impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15 if changed else 6.42 * iss
    exploit = 8.22 * AV[m["AV"]] * AC[m["AC"]] * pr * UI[m["UI"]]
    if impact <= 0:
        return 0.0
    return roundup(min((1.08 if changed else 1.0) * (impact + exploit), 10.0))


def bucket(score: float) -> str:
    return "CRITICAL" if score >= 9 else "HIGH" if score >= 7 else "MODERATE" if score >= 4 else "LOW" if score > 0 else "NONE"


# --------------------------------------------------------------------- reading a record


def fixed_versions(record: dict, ecosystem: str, name: str) -> list[str]:
    """A record's 'affected' list says, per package, which version ranges are vulnerable.
    A range is a list of events: {"introduced": "0"} opens it, {"fixed": "2.20.0"} closes it.
    Ranges of type GIT use commit hashes; only ECOSYSTEM and SEMVER ranges hold real versions."""
    out = []
    for aff in record.get("affected", []):
        pkg = aff.get("package", {})
        if pkg.get("ecosystem") != ecosystem or pkg.get("name") != name:
            continue
        for rng in aff.get("ranges", []):
            if rng["type"] in ("ECOSYSTEM", "SEMVER"):
                out += [ev["fixed"] for ev in rng["events"] if "fixed" in ev]
    return out


def main() -> None:
    # 1. Which advisories affect requests 2.19.1? /v1/query answers with full records.
    answer = post(f"{OSV}/v1/query", {"package": {"name": "requests", "ecosystem": "PyPI"}, "version": "2.19.1"})
    vulns = answer["vulns"]
    print(f"{len(vulns)} records for requests 2.19.1:")
    for v in vulns:
        print(f"  {v['id']:<22} aliases={v.get('aliases', [])}")
    ids = {v["id"] for v in vulns}

    # 2. Notice: the same problem is filed under several ids (GHSA-..., PYSEC-..., CVE-...).
    #    Databases publish independently and list each other as 'aliases'. A report that
    #    counts records instead of problems double-counts. Module 06 merges them.
    ghsa = next(v for v in vulns if v["id"] == "GHSA-x84v-xcm2-53pg")
    assert "CVE-2018-18074" in ghsa["aliases"]

    # 3. Fetch that one record directly.
    record = get(f"{OSV}/v1/vulns/GHSA-x84v-xcm2-53pg")
    assert record["id"] == "GHSA-x84v-xcm2-53pg" and "GHSA-x84v-xcm2-53pg" in ids
    print("\nsummary:", record["summary"])

    # 4. Severity. This record carries a CVSS v3 vector; we compute the score ourselves.
    vector = next(s["score"] for s in record["severity"] if s["type"] == "CVSS_V3")
    score = cvss3_score(vector)
    print(f"severity: {vector} -> {score} ({bucket(score)})")
    assert (score, bucket(score)) == (7.5, "HIGH")

    # 5. The fix.
    fixed = fixed_versions(record, "PyPI", "requests")
    print("fixed in:", fixed)
    assert fixed == ["2.20.0"]

    # 6. A version AFTER the fix is clean for this advisory.
    newer = post(f"{OSV}/v1/query", {"package": {"name": "requests", "ecosystem": "PyPI"}, "version": "2.20.0"})
    assert "GHSA-x84v-xcm2-53pg" not in {v["id"] for v in newer.get("vulns", [])}

    # 7. A package OSV has never heard of returns {} (no 'vulns' key), not an error.
    nothing = post(f"{OSV}/v1/query", {"package": {"name": "certifi", "ecosystem": "PyPI"}, "version": "2099.1.1"})
    assert nothing.get("vulns", []) == []

    # The CVSS calculator against vectors with published scores:
    assert cvss3_score("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H") == 9.8
    assert cvss3_score("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H") == 10.0
    print("OK")


if __name__ == "__main__":
    main()
