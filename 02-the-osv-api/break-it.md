# Break It: The OSV API

## Challenge 1: The Wrong Ecosystem Spelling

Change `"PyPI"` to `"pypi"` in the first query and run it. What does OSV answer, and what would a scanner that does this report?

**Hint:** The ecosystem is case-sensitive. A mismatch does not produce an error; it produces `{}`, which looks exactly like "no vulnerabilities".
This is the most dangerous kind of failure for an audit tool: a silent clean bill of health. Think about how you would guard against it (a test that a known-bad pin *is* reported is the cheapest answer).

## Challenge 2: Count Problems, Not Records

Print `len(vulns)` and then count distinct problems by following `aliases`. What do you get for `requests 2.19.1`?

**Hint:** Ten records, five problems today. Group records whose id sets overlap. Module 06 does it with a few lines of set logic.

## Challenge 3: Which Fix?

Fetch `GHSA-xvch-5gv4-984h` (minimist) and print `fixed_versions(record, "npm", "minimist")`. You should see more than one version.
If you run `minimist 0.0.8`, which one do you want?

**Hint:** One fix per release branch (for example `0.2.4` and `1.2.6`). The useful answer is the smallest fixed version *above the installed one*; module 06 implements it.

## Challenge 4: A Score You Cannot Compute

Find a record whose only severity is a `CVSS_V4` vector (try recent GHSA records). What does `cvss3_score` do with it? What should the report say?

**Hint:** v4 uses different metrics and a lookup-table scoring system, and is out of scope here. The rule is: never invent a number. Fall back to the record's own label, and if there is none, print UNKNOWN.
