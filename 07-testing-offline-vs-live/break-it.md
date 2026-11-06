# Break It: Testing Offline vs Live

## Challenge 1: Exact Counts on the Live API

In `test_known_vulnerable_pin_is_reported`, also assert `out.count("requests 2.19.1") == 5`. Run both suites.

**Hint:** It passes offline (the recording has five) and will fail live the day a sixth advisory is published. Tests against a changing world should assert facts that cannot change.

## Challenge 2: Remove the Unrecorded Check

Delete `assert r.unrecorded == []` from the `osv` fixture. Write a test that scans a `tmp_path` `requirements.txt` containing `flask==0.5` (not in the recording) and run `pytest -m "not live"`.

**Hint:** The fake answers "no vulnerabilities" for it and the test still passes. A recording that cannot say "I don't know" hides gaps. Restore the check and rerecord with `--record`.

## Challenge 3: Mock the Wrong Layer

Replace the replay server with `monkeypatch.setattr(server, "http_json", lambda *a, **k: {...})`. Now break `osv_base()` (return a wrong URL). Do the tests notice?

**Hint:** No: the mock sits above the code that builds the URL. The socket-level replay catches this because a wrong URL gets a 404.

## Challenge 4: Another Failure

Add a test where the replay server answers `200` with a body that is not JSON (`b"<html>"`). What does the scan do? What should it do?

**Hint:** A proxy login page is a classic. `json.loads` raises `JSONDecodeError`, which is not an `AuditError`, so the agent sees a generic error. Convert it, with a message that names the URL.

## Challenge 5: Schedule the Live Run

Write the GitHub Actions job that runs `pytest -m live` weekly and on demand but never on pull requests.

**Hint:** `on: schedule: - cron: "0 6 * * 1"` plus `workflow_dispatch`, and `if: github.event_name != 'pull_request'` on the job. See the full server's `.github/workflows/ci.yml`.
