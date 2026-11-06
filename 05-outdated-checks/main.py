"""Module 05: how far behind is this version?

Three problems:

  1. Compare versions correctly. "1.10" > "1.9" (compare numbers, not strings), and
     "2.0.0rc1" < "2.0.0" (a pre-release sorts BEFORE its release).
  2. Ask each registry for the latest version. Every registry has its own endpoint:
        PyPI   GET https://pypi.org/pypi/<name>/json            -> info.version
        npm    GET https://registry.npmjs.org/<name>/latest     -> version
     Scoped npm names (@babel/core) must have the slash percent-encoded in the URL path.
  3. Do it for many packages without being rude: a small thread pool, de-duplication, and
     per-package failures reported instead of hidden.

Real network, standard library only.

Run:  python main.py
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

# --------------------------------------------------------------------- 1. versions

HEAD = re.compile(r"^v?(?:\d+!)?(\d+(?:\.\d+)*)(.*)$", re.I)
PRE = ("a", "b", "c", "rc", "alpha", "beta", "pre", "preview", "dev")


def key(version: str) -> tuple | None:
    """A sortable key: (release numbers, stage, tail). stage 0 = pre-release, 1 = final, 2 = post-release.
    Tuples compare element by element, which is exactly the ordering we want."""
    m = HEAD.match(version.strip())
    if not m:
        return None  # a git hash or "latest": cannot be ordered, so do not pretend
    nums = [int(x) for x in m.group(1).split(".")]
    while len(nums) > 1 and nums[-1] == 0:  # 1.0 == 1.0.0
        nums.pop()
    rest = m.group(2).split("+")[0].lower()  # "+build" metadata never affects ordering
    tokens = re.findall(r"\d+|[a-z]+", rest)
    tail = tuple((0, int(t)) if t.isdigit() else (1, t) for t in tokens)
    if not rest:
        return (tuple(nums), 1, ())
    if tokens and tokens[0] in ("post", "p"):
        return (tuple(nums), 2, tail)
    if tokens and (tokens[0] in PRE or rest.startswith("-")):
        return (tuple(nums), 0, tail)
    return None


def gap(installed: str, latest: str) -> str | None:
    """'major' / 'minor' / 'patch' if latest is newer, else None."""
    ki, kl = key(installed), key(latest)
    if ki is None or kl is None or kl <= ki:
        return None
    pad = lambda k: (list(k[0]) + [0, 0, 0])[:3]  # noqa: E731
    (a, b, _), (x, y, _) = pad(ki), pad(kl)
    return "major" if x != a else "minor" if y != b else "patch"


# --------------------------------------------------------------------- 2. registries


def get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "depaudit-tutorial/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def latest(ecosystem: str, name: str) -> str:
    if ecosystem == "PyPI":
        return get_json(f"https://pypi.org/pypi/{name}/json")["info"]["version"]
    if ecosystem == "npm":
        return get_json(f"https://registry.npmjs.org/{urllib.parse.quote(name, safe='@')}/latest")["version"]
    raise ValueError(f"no registry known for {ecosystem}")


# --------------------------------------------------------------------- 3. many at once


def latest_many(pkgs: list[tuple[str, str]], workers: int = 8) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], str]]:
    """Returns (found, failed). A failed lookup is REPORTED: silently skipping it would make
    "nothing is outdated" and "I could not check" look the same."""

    def one(k: tuple[str, str]) -> tuple[str | None, str | None]:
        try:
            return latest(*k), None
        except Exception as e:  # noqa: BLE001 - network errors of many kinds; we record the message
            return None, f"{type(e).__name__}: {e}"

    unique = list(dict.fromkeys(pkgs))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, unique))
    found = {k: v for k, (v, _) in zip(unique, results) if v}
    failed = {k: err for k, (_, err) in zip(unique, results) if err}
    return found, failed


def main() -> None:
    # 1. Comparison edge cases.
    assert key("1.10") > key("1.9")  # numbers, not strings ("1.10" < "1.9" as text!)
    assert key("1.0") == key("1.0.0")
    assert key("2.0.0rc1") < key("2.0.0") < key("2.0.0.post1")
    assert key("1.0.0-beta.2") < key("1.0.0-beta.10")
    assert key("deadbeef") is None
    assert gap("2.19.1", "3.0.0") == "major"
    assert gap("2.19.1", "2.20.0") == "minor"
    assert gap("2.19.1", "2.19.2") == "patch"
    assert gap("2.19.1", "2.19.1") is None and gap("3.0", "2.0") is None

    # 2. Live lookups.
    req_latest = latest("PyPI", "requests")
    lodash_latest = latest("npm", "lodash")
    babel_latest = latest("npm", "@babel/core")  # scoped name: '/' percent-encoded
    print("latest requests:", req_latest, "| lodash:", lodash_latest, "| @babel/core:", babel_latest)
    assert gap("2.19.1", req_latest) in ("minor", "major")
    assert gap("4.17.15", lodash_latest) is not None
    assert key(babel_latest) is not None

    # 3. Concurrency + honest failures.
    found, failed = latest_many([("PyPI", "requests"), ("npm", "lodash"), ("PyPI", "requests"), ("PyPI", "no-such-package-zzz-123")])
    assert set(found) == {("PyPI", "requests"), ("npm", "lodash")}, found
    assert list(failed) == [("PyPI", "no-such-package-zzz-123")] and "404" in failed[("PyPI", "no-such-package-zzz-123")]
    print("failed lookup reported:", failed)
    print("OK")


if __name__ == "__main__":
    main()
