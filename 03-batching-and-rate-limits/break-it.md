# Break It: Batching and Rate Limits

## Challenge 1: Ignore the Page Token

Delete the `if res.get("next_page_token")` branch and run `main.py`. Which assertion fails first?

**Hint:** `requests` would report one advisory instead of three, and nothing would complain. This is why the fake server paginates by one: it is a test that would catch the bug on day one.

## Challenge 2: Believe Retry-After

Make the fake server send `Retry-After: 3600` and remove the `min(..., max_wait)` cap. How long does a scan take?

**Hint:** An hour of silence from a tool call. Servers (and proxies) send surprising values; cap them, and prefer a clear error to an unbounded wait.

## Challenge 3: Swallow the Error

Replace the final `raise RateLimited(...)` with `return {}`. Rerun. Which test catches it? What would your agent tell the user?

**Hint:** "No vulnerabilities found", after OSV refused to answer. Write the test first next time: `fake = FakeOSV(fail_first=100)` and assert an exception.

## Challenge 4: Unbounded Parallelism

Set `workers=200` and fetch 200 records. Does it get faster? What does a polite client look like to the server?

**Hint:** Past a handful of parallel connections you gain little and risk 429s, which the retry logic then turns into delays. Eight is a courtesy.

## Challenge 5: A Token Loop

Make the fake server always return a `next_page_token`. What happens? Add a maximum number of pages to `query_batch`.

**Hint:** A loop that trusts the server to terminate will not, one day. The real server code stops after 50 pages with an error.
