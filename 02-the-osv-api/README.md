# Module 02: The OSV API

## The Concept

[OSV.dev](https://osv.dev) is an open database that aggregates advisories from GitHub (GHSA), PyPI (PYSEC),
RustSec, the Go vulnerability database, npm and many others, in one JSON schema. No key, no account.
Three endpoints are enough for an audit:

| Endpoint | Question | Answer |
|---|---|---|
| `POST /v1/query` | "is this package version affected?" | full advisory records |
| `POST /v1/querybatch` | the same, for many versions at once | **only ids** (module 03) |
| `GET /v1/vulns/{id}` | "what is GHSA-x84v-xcm2-53pg?" | one full record |

A query is a package and an exact version:

```json
{"package": {"name": "requests", "ecosystem": "PyPI"}, "version": "2.19.1"}
```

The ecosystem names are OSV's, case-sensitive: `PyPI`, `npm`, `crates.io`, `Go`. That is why `Pkg.ecosystem` in module 01 uses them verbatim.
OSV does the version arithmetic for you: it knows each advisory's affected ranges and answers whether *this* version falls inside one.
Unknown packages are not an error; the answer is just `{}`.

## One problem, several records

Running `main.py` prints this for `requests 2.19.1`:

```
10 records for requests 2.19.1:
  GHSA-x84v-xcm2-53pg    aliases=['CVE-2018-18074', 'PYSEC-2018-28']
  PYSEC-2018-28          aliases=['CVE-2018-18074', 'GHSA-x84v-xcm2-53pg']
  ...
```

Ten records, **five** problems. GitHub, PyPI's advisory database and NVD each published their own entry, and they list each other as `aliases`.
A tool that counts records tells you "10 vulnerabilities" and is wrong by 2x. Module 06 merges records into problems.

## Reading a record

```json
{
  "id": "GHSA-x84v-xcm2-53pg",
  "summary": "Insufficiently Protected Credentials in Requests",
  "aliases": ["CVE-2018-18074", "PYSEC-2018-28"],
  "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N"}],
  "affected": [{
    "package": {"ecosystem": "PyPI", "name": "requests"},
    "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2.20.0"}]}]
  }]
}
```

- **Severity** is often a CVSS *vector*, not a number. The score is computed from the vector by a published formula (FIRST.org CVSS 3.1, section 7.1);
  `cvss3_score()` implements it in 10 lines. Buckets: 9.0+ critical, 7.0+ high, 4.0+ moderate, above 0 low. Some records carry no vector but a label in
  `database_specific.severity`; some carry neither, and the honest label is UNKNOWN.
- **`affected[].ranges[].events`** is a sequence: `introduced: 0` opens a vulnerable range, `fixed: 2.20.0` closes it. A package can have several ranges
  (a bug fixed in both 1.x and 2.x lists two `fixed`s). A `GIT` range uses commit hashes, not versions, so only `ECOSYSTEM` and `SEMVER` ranges are read.
- The same record can mention several packages in `affected`; filter on ecosystem *and* name.

## Run It

```bash
python 02-the-osv-api/main.py
```

It queries the real API, asserts that `requests 2.19.1` is affected by `GHSA-x84v-xcm2-53pg`, that its score is 7.5 (HIGH), that the fix is `2.20.0`,
that `2.20.0` is clean for this advisory, and that an unknown version of a real package returns no vulnerabilities.

## Key Takeaways

- Look up **exact** versions in **exact** ecosystem spellings.
- Records are not problems; aliases link them.
- Compute severity from the vector, fall back to the label, and say UNKNOWN when neither exists.
- "Fixed in" is a list of events per package, not a field.
