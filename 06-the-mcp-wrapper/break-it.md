# Break It: The MCP Wrapper

## Challenge 1: Print to Stdout

Add `print("scanning", path)` at the top of `scan_project` and run the demo. Then change it to `print(..., file=sys.stderr)`.

**Hint:** In `--serve` mode stdout carries JSON-RPC. A stray line corrupts the stream; depending on the SDK version the client skips it, errors, or hangs. stderr is free for logs.

## Challenge 2: Let the Exception Out

Remove the `try/except` in `scan_project` and call it with a bad path in the demo. What does the client's error text say now?

**Hint:** `Error executing tool scan_project`, and nothing else. The agent cannot tell a typo from a crash. Put the `try/except` back and compare.

## Challenge 3: Catch Everything

Change `except AuditError` to `except Exception`. Now introduce a bug (`records[v]` with a typo'd key). What does the agent see?

**Hint:** A friendly-looking message hiding a stack trace you will never see. Catch what you can explain; let the rest be loud.

## Challenge 4: First Fix, Not Smallest Fix

Change `fixed_in` to return `fixes[0]`. Run the demo and look at the `minimist` line.

**Hint:** It will suggest a version one or two majors away, because advisories list one fix per release branch. An agent will faithfully recommend a breaking upgrade.

## Challenge 5: Double-count Aliases

Replace `merge_aliases(...)` with `[[r] for r in records]` and compare the number of lines for `requests 2.19.1` in `requirements.txt`.

**Hint:** Every GHSA/PYSEC pair becomes two lines for one flaw. The report doubles in size and the counts lie.
