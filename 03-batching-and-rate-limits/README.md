# Module 03: Batching and Rate Limits

## The Concept

A real lockfile has hundreds of packages. One request each is hundreds of round trips, and a good way to get rate limited.
OSV offers `POST /v1/querybatch`: up to 1000 queries in one request, one result per query in the same order. The catch is that the answer carries
**ids only**; you then fetch each distinct advisory once.

```
packages (500)  ──querybatch──►  ids per package  ──dedupe──►  distinct ids  ──GET /v1/vulns/{id} x N (8 at a time)──►  records
```

## Four things to get right

### 1. Deduplicate before asking

Lockfiles repeat packages (the same `urllib3 1.23` pulled in by three parents). `dict.fromkeys(pkgs)` removes duplicates and keeps order.
Fetch each advisory once, even when ten packages share it.

### 2. Chunk

Send at most N queries per request (the server uses 500; the limit is 1000). Chunking also bounds the memory and time of any single call.

### 3. Pagination: a result can be cut short

A single query's result may come back with a `next_page_token`. It means "there are more advisories for this package; ask again with the token".
If you ignore it, a heavily vulnerable package silently shows fewer problems than it has: the worst possible bug for an audit tool.

```python
pending = [(i, None) for i in range(len(part))]       # start: page one for everyone
while pending:
    results = post(querybatch, queries_for(pending))["results"]
    pending = [(i, res["next_page_token"]) for (i, _), res in zip(pending, results) if res.get("next_page_token")]
```

Only the queries that were cut short are asked again, with their tokens, and the loop ends when nobody has a token left.
`main.py` proves this with a fake server that paginates by 1: `requests` has three advisories, three pages.

### 4. Rate limits: retry a little, then fail loudly

HTTP 429 means "slow down". The rules in `request_json`:

- retry only what might be temporary (429, 502, 503, 504), a few times;
- honour `Retry-After`, but **cap it**: an agent should not sit silent for an hour because a header said 3600;
- when the attempts run out, raise an error that states what happened and what to do. Never return `[]`.

For a human or an agent, "OSV rate limited us, wait a minute" is information. An empty list is a lie.

## Concurrency for the record fetches

After batching you have maybe 40 distinct ids to download. The work is waiting on the network, so a thread pool is the right tool and the GIL is irrelevant:

```python
with ThreadPoolExecutor(max_workers=8) as pool:
    records = dict(zip(unique, pool.map(one, unique)))
```

Eight workers is a courtesy limit, not a technical one. `pool.map` returns results in input order, so zipping with the ids is safe, and an exception in any worker is re-raised in the caller.

## Test it without the real service

Pagination and 429s are rare on the real API, so `main.py` includes `FakeOSV`, a small `http.server` that paginates by one and can answer 429 first.
It listens on a real local port, so the real `urllib` code runs. The retry test passes a `sleep=` function that records instead of sleeping, so it asserts
`[2.0, 2.0]` (the server's `Retry-After`) without waiting.

## Run It

```bash
python 03-batching-and-rate-limits/main.py
```

Part A (fake server) checks pagination, chunking, recovery after two 429s, and the final error. Part B sends three real packages in one request and fetches the resulting records concurrently.

## Key Takeaways

- Dedupe, chunk, paginate, and fetch each record once.
- Make timing injectable (`sleep=`) so retry logic is testable in milliseconds.
- A failed lookup must never look like a successful empty one.
