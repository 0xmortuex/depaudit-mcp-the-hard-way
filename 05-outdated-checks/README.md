# Module 05: Outdated Checks

## The Concept

Vulnerabilities are the urgent half of dependency health. The slow half is drift: you are on `2.19.1`, the world is on `2.34.2`, and the
longer the gap, the more painful the eventual upgrade. "How far behind, and how big a jump?" needs two ingredients: the latest version from the registry,
and a way to compare versions.

## 1. Comparing versions

Strings do not work: `"1.10" < "1.9"` as text. Compare *numbers*. Real version schemes add pre-releases (`2.0.0rc1`, `1.0.0-beta.2`)
that sort **before** their release, and post-releases (`1.0.post1`) that sort after. `key()` maps a version to a tuple that sorts correctly:

```
2.0.0rc1  ->  ((2,), 0, (rc, 1))      stage 0 = pre-release
2.0.0     ->  ((2,), 1, ())           stage 1 = final
2.0.0.post1 -> ((2,), 2, (post, 1))   stage 2 = post-release
```

Python compares tuples element by element, so `(2,), 0, ...` < `(2,), 1, ...`. Trailing zeros are stripped (`1.0 == 1.0.0`), build metadata (`+abc`) is ignored, and
anything that is not a version (a git hash, `latest`) returns `None` so callers can refuse to order it instead of guessing.

`gap()` then labels the jump by the first release number that differs: **major**, **minor** or **patch**. This is the same signal semver gives you about breaking changes
(and why the full server also flags a minor bump on `0.x`, where semver says anything may break).

This is deliberately *not* a full PEP 440 or semver implementation. It covers what lockfiles pin and what registries publish as "latest". Say where your approximation ends.

## 2. Asking each registry

| Ecosystem | Request | Field |
|---|---|---|
| PyPI | `GET https://pypi.org/pypi/<name>/json` | `info.version` |
| npm | `GET https://registry.npmjs.org/<name>/latest` | `version` |

Details: scoped npm names (`@babel/core`) need the slash percent-encoded (`@babel%2Fcore`), which `urllib.parse.quote(name, safe='@')` does.
PyPI wants the normalized name. Both are cacheable; the server keeps results for an hour. Send a `User-Agent` that identifies you; some registries (crates.io) require one.

"Latest" means latest *stable*: the registries already skip pre-releases for these endpoints.

## 3. Many packages, honestly

```python
with ThreadPoolExecutor(max_workers=8) as pool:
    results = list(pool.map(one, unique))
```

The important line is in `one()`: it catches the failure and returns the **message**. The caller gets `(found, failed)` and prints the failures. Why not just skip failures?
Because "nothing is outdated" and "I could not check" would look identical. The full server also raises if **every** lookup failed, since that means the network, not the packages.

## Run It

```bash
python 05-outdated-checks/main.py
```

Asserts the comparison edge cases, then queries PyPI and npm for real (including a scoped name) and checks that a nonexistent package is *reported* as a failed lookup with its 404.

## Key Takeaways

- Compare versions as tuples of numbers with a stage for pre/post releases.
- Return `None` for things you cannot order.
- Report failed lookups; never turn them into silence.
