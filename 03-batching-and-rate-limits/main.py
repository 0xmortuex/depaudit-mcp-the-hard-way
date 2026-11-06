"""Module 03: ask about hundreds of packages without hundreds of round trips.

    /v1/querybatch  up to 1000 queries per request, answers with IDs only
    next_page_token a result can be cut short; you must ask again with its token
    /v1/vulns/{id}  then fetch each distinct record ONCE, concurrently
    HTTP 429        back off, honour Retry-After, and eventually fail loudly

Two halves, both verified for real:

  A. a tiny local server that behaves like OSV (pages of 1, a few 429s first),
     so pagination and retries are exercised deterministically;
  B. the same code against the live api.osv.dev.

Run:  python main.py
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, NamedTuple

OSV = "https://api.osv.dev"


class Pkg(NamedTuple):
    ecosystem: str
    name: str
    version: str


class RateLimited(Exception):
    pass


# --------------------------------------------------------------------- HTTP with retries


def request_json(req: urllib.request.Request, retries: int = 3, sleep=time.sleep, max_wait: float = 10.0) -> Any:
    """Send a request; retry 429 and 5xx a few times; raise a clear error at the end.

    Rules worth copying:
      * only retry what is plausibly temporary (429, 502, 503, 504);
      * obey Retry-After when the server sends it, but cap it - an agent should not
        sit silent for an hour because a server said 3600;
      * after the last attempt, raise something the agent can act on, never return [].
    """
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503, 504) and attempt < retries:
                wait = e.headers.get("Retry-After")
                sleep(min(float(wait), max_wait) if wait else min(0.5 * 2**attempt, max_wait))
                continue
            if e.code == 429:
                raise RateLimited(f"{req.full_url} answered HTTP 429 {retries + 1} times; wait a minute and retry") from e
            raise


def post_json(url: str, body: dict, **kw: Any) -> Any:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    return request_json(req, **kw)


# --------------------------------------------------------------------- batching


def query_batch(pkgs: list[Pkg], base: str = OSV, chunk: int = 500, **kw: Any) -> dict[Pkg, list[str]]:
    """Advisory IDs for every package. Chunks of `chunk` queries, then page tokens."""
    unique = list(dict.fromkeys(pkgs))  # dedupe, keep order: lockfiles repeat packages
    out: dict[Pkg, list[str]] = {p: [] for p in unique}
    for start in range(0, len(unique), chunk):
        part = unique[start : start + chunk]
        # (index in part, page token). Everything starts at page one with no token.
        pending: list[tuple[int, str | None]] = [(i, None) for i in range(len(part))]
        while pending:
            queries = []
            for i, token in pending:
                q: dict[str, Any] = {"package": {"name": part[i].name, "ecosystem": part[i].ecosystem}, "version": part[i].version}
                if token:
                    q["page_token"] = token
                queries.append(q)
            results = post_json(f"{base}/v1/querybatch", {"queries": queries}, **kw)["results"]
            assert len(results) == len(pending), "OSV answers one result per query, in order"
            nxt = []
            for (i, _), res in zip(pending, results):
                out[part[i]] += [v["id"] for v in res.get("vulns", [])]
                if res.get("next_page_token"):  # the answer was cut short: ask for the rest
                    nxt.append((i, res["next_page_token"]))
            pending = nxt
    return out


def fetch_records(ids: list[str], base: str = OSV, workers: int = 8, **kw: Any) -> dict[str, dict]:
    """Each distinct record once, on a small thread pool. Threads suit this: the work is
    waiting for the network, so the GIL is not a bottleneck. 8 workers is polite."""
    unique = list(dict.fromkeys(ids))

    def one(vid: str) -> dict:
        return request_json(urllib.request.Request(f"{base}/v1/vulns/{vid}"), **kw)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(zip(unique, pool.map(one, unique)))


# --------------------------------------------------------------------- half A: a fake OSV


class FakeOSV:
    """Answers /v1/querybatch like OSV does, but with a page size of 1 and a few 429s first."""

    DATA = {"requests": ["GHSA-1", "GHSA-2", "GHSA-3"], "urllib3": ["GHSA-4"], "certifi": []}

    def __init__(self, fail_first: int = 0, retry_after: str = "0") -> None:
        self.fail_first = fail_first
        self.requests_seen = 0
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a: Any) -> None:
                pass

            def do_POST(self) -> None:
                outer.requests_seen += 1
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if outer.requests_seen <= outer.fail_first:
                    self.send_response(429)
                    self.send_header("Retry-After", retry_after)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                results = []
                for q in body["queries"]:
                    ids = outer.DATA[q["package"]["name"]]
                    start = int(q.get("page_token", 0))
                    res: dict[str, Any] = {"vulns": [{"id": i} for i in ids[start : start + 1]]}
                    if start + 1 < len(ids):
                        res["next_page_token"] = str(start + 1)
                    results.append(res if res["vulns"] else {})
                raw = json.dumps({"results": results}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self.server.shutdown()


def main() -> None:
    pk = [Pkg("PyPI", "requests", "1"), Pkg("PyPI", "urllib3", "1"), Pkg("PyPI", "certifi", "1"), Pkg("PyPI", "requests", "1")]

    # A1. Pagination: requests has 3 advisories but each page holds 1.
    fake = FakeOSV()
    got = query_batch(pk, base=fake.url)
    assert got[Pkg("PyPI", "requests", "1")] == ["GHSA-1", "GHSA-2", "GHSA-3"], got
    assert got[Pkg("PyPI", "certifi", "1")] == []
    assert fake.requests_seen == 3, "page 1 for all three packages, then two more pages for requests"
    fake.stop()
    print("pagination:", got)

    # A2. Chunking: chunk=2 over three unique packages = 2 batches (+ pages).
    fake = FakeOSV()
    query_batch(pk, base=fake.url, chunk=2)
    assert fake.requests_seen == 4  # batch1 (requests, urllib3) + 2 more pages for requests; batch2 (certifi)
    fake.stop()

    # A3. Rate limit, recovered: two 429s with Retry-After, then success. We pass a fake
    # `sleep` so the test does not actually wait, and check it was asked to wait as told.
    waits: list[float] = []
    fake = FakeOSV(fail_first=2, retry_after="2")
    got = query_batch([Pkg("PyPI", "urllib3", "1")], base=fake.url, sleep=waits.append)
    assert got[Pkg("PyPI", "urllib3", "1")] == ["GHSA-4"] and waits == [2.0, 2.0], waits
    fake.stop()

    # A4. Rate limit, not recovered: the error says what happened and what to do.
    fake = FakeOSV(fail_first=100)
    try:
        query_batch([Pkg("PyPI", "urllib3", "1")], base=fake.url, sleep=lambda s: None, retries=2)
    except RateLimited as e:
        print("gave up:", e)
        assert "HTTP 429 3 times" in str(e)
    else:
        raise AssertionError("expected RateLimited")
    fake.stop()

    # B. The real thing: three packages in ONE request, then the records concurrently.
    live = [Pkg("PyPI", "requests", "2.19.1"), Pkg("npm", "lodash", "4.17.15"), Pkg("PyPI", "certifi", "2099.1.1")]
    t0 = time.time()
    ids = query_batch(live)
    assert "GHSA-x84v-xcm2-53pg" in ids[live[0]] and ids[live[1]] and ids[live[2]] == []
    all_ids = [i for v in ids.values() for i in v]
    records = fetch_records(all_ids)
    assert all(records[i]["id"] == i for i in all_ids)
    print(f"live: {len(live)} packages -> {len(all_ids)} advisory ids -> {len(records)} records in {time.time() - t0:.1f}s")
    print("OK")


if __name__ == "__main__":
    main()
