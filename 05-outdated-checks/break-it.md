# Break It: Outdated Checks

## Challenge 1: Compare as Strings

Replace `key(a) < key(b)` comparisons with plain string comparison and check `1.10` against `1.9`.

**Hint:** `"1.10" < "1.9"` is true as text. A tool built this way says 1.9 is newer than 1.10.

## Challenge 2: A Pre-release Is Not Newer

What does your code say about installed `2.0.0` vs `2.0.0rc1`? Remove the stage element from the key and try again.

**Hint:** Without a stage, `2.0.0rc1` and `2.0.0` tie or sort wrongly, and the tool recommends "upgrading" from a final release back to a release candidate.

## Challenge 3: Hide the Failures

In `latest_many`, change the `except` to `return None, None`. Run with a nonexistent package.

**Hint:** The package disappears from both `found` and `failed`. The report shows fewer rows and no hint that anything was skipped. Which assertion in `main.py` notices?

## Challenge 4: Add crates.io

Add `latest("crates.io", name)`: `GET https://crates.io/api/v1/crates/<name>` and read `crate.max_stable_version`. Try it without a `User-Agent`.

**Hint:** crates.io rejects requests without an identifying User-Agent. Registries have house rules; read them before hammering one with eight threads.
