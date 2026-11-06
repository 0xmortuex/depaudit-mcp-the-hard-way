# Module 07: Testing Offline vs Live

## The Concept

The server's output depends on a service you do not control. Test it only against the live API and CI fails whenever OSV is down, slow, or has just published
a new advisory. Test it only against mocks and you can be green while the real API has changed shape. You need both, with different jobs:

| | Offline (replay) | Live |
|---|---|---|
| Runs | every push | on a schedule, and before releases |
| Needs internet | no | yes |
| Catches | your bugs | the world changing under you |
| Can inject failures | yes (429, 500, unreachable) | no |
| Pass criteria | exact, deterministic | **stable facts only** |

## Replay over a real socket

`replay.py` is a small `http.server` that answers `POST /v1/querybatch` and `GET /v1/vulns/{id}` from `recorded.json`. The code under test talks to it by setting
`MINIDEP_OSV_URL`, and everything real still runs: URL building, JSON encoding, parsing, HTTP error mapping. A mock that replaces the function doing HTTP skips all of that.
(The same base-URL switch exists in the full server as `DEPAUDIT_OSV_URL`.)

The recording is produced by the code itself:

```bash
python 07-testing-offline-vs-live/main.py --record
```

It scans the sample lockfiles against the real API and stores the ids per package and the advisory records (trimmed to the fields the code reads).
The fake server also collects `unrecorded`: any question the recording cannot answer. The `osv` fixture asserts that list is empty, so a test that wanders outside the recording fails loudly instead of quietly getting "no vulnerabilities".

## One test, two sources

```python
@pytest.fixture(params=["offline", pytest.param("live", marks=pytest.mark.live)])
def osv(request, monkeypatch): ...
```

Each of the first three tests runs twice with identical assertions: once against the replay, once against the real service (selected by the `live` marker, registered in `pytest.ini`).

```bash
pytest -m "not live"    # offline: fast, deterministic, CI on every push
pytest -m live          # real api.osv.dev
```

Identical assertions are the point: they stop the recording from quietly drifting into testing behaviour the real API does not have.

### What a live test may assert

Not "exactly 9 advisories": that changes the day someone files a new one. Assert **stable facts**:

- a long-known-vulnerable pin (`requests 2.19.1`, `lodash 4.17.15`) *is* reported, with its known fix `2.20.0`;
- the dependency chain `mkdirp 0.5.1 > minimist 0.0.8` appears (it comes from the lockfile, not OSV);
- output is sorted worst-first.

## Fault injection: what only a fake can do

The real service will not return a 429 on demand. The replay server can:

```python
def test_rate_limit_becomes_an_actionable_error(replay):
    replay.fail_status = 429
    with pytest.raises(server.AuditError, match="HTTP 429.*rate limiting.*wait a minute"): ...
```

Three failure tests matter most for an audit tool, and each guards against the same disaster, **reporting a clean scan when the check did not happen**:
rate limited (429), server error (500), and unreachable (nothing listening on the port).

## Run It

```bash
pip install -r requirements.txt
python 07-testing-offline-vs-live/main.py
```

`main.py` runs the offline suite and then the live suite, and requires both to pass.

## In CI (what the full server does)

```yaml
test:    pytest tests            # offline, on every push, 3 OSes
live:    pytest tests -m live    # weekly + manual, so an outage never blocks a pull request
```

## Key Takeaways

- Replay over a real socket; do not mock away the code you are testing.
- Assert stable facts against the live service; exact output only against recordings.
- Make "the recording is missing this" a failure.
- Test failure paths, because for a security tool the quiet failure is the worst one.
