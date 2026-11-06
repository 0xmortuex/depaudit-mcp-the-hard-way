"""Tests for the module 06 server's scan(): offline by default, live on request.

    pytest              offline only (what CI runs on every push)
    pytest -m live      the real api.osv.dev

The SAME assertions are used for both, through the `osv` fixture, so the recording can
never drift into testing something the real API does not do - and when it does drift
(a new advisory appears), only the live run notices, on a schedule, without blocking anyone.
"""

import importlib.util
import os

import pytest

from replay import Replay

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "..", "samples")

# The code under test is module 06's main.py, loaded by file path (its folder name starts
# with a digit, so `import` cannot name it).
spec = importlib.util.spec_from_file_location("server06", os.path.join(HERE, "..", "06-the-mcp-wrapper", "main.py"))
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


@pytest.fixture
def replay(monkeypatch):
    r = Replay()
    monkeypatch.setenv("MINIDEP_OSV_URL", r.url)
    yield r
    r.stop()


@pytest.fixture(params=["offline", pytest.param("live", marks=pytest.mark.live)])
def osv(request, monkeypatch):
    """Where OSV answers come from: a replay of a recording, or the real service."""
    if request.param == "offline":
        r = Replay()
        monkeypatch.setenv("MINIDEP_OSV_URL", r.url)
        yield r
        assert r.unrecorded == [], f"the recording is missing answers: {r.unrecorded}"
        r.stop()
    else:
        monkeypatch.delenv("MINIDEP_OSV_URL", raising=False)
        yield None


def test_known_vulnerable_pin_is_reported(osv):
    out = server.scan(os.path.join(SAMPLES, "requirements.txt"))
    assert "requests 2.19.1" in out and "(fixed in 2.20.0)" in out


def test_transitive_vulnerability_shows_its_chain(osv):
    out = server.scan(os.path.join(SAMPLES, "npm"))
    assert "35 packages, 3 direct, 32 transitive" in out
    assert "lodash 4.17.15" in out
    assert "via mkdirp 0.5.1 > minimist 0.0.8" in out


def test_worst_first(osv):
    rows = [ln.split()[0] for ln in server.scan(os.path.join(SAMPLES, "npm")).splitlines()
            if ln.split() and ln.split()[0] in server.ORDER]
    assert rows == sorted(rows, key=server.ORDER.index)


# ---- failure modes: only practical offline, because the real service will not misbehave on request


def test_rate_limit_becomes_an_actionable_error(replay):
    replay.fail_status = 429
    with pytest.raises(server.AuditError, match="HTTP 429.*rate limiting.*wait a minute"):
        server.scan(os.path.join(SAMPLES, "requirements.txt"))


def test_server_error_is_not_mistaken_for_a_clean_scan(replay):
    replay.fail_status = 500
    with pytest.raises(server.AuditError, match="HTTP 500"):
        server.scan(os.path.join(SAMPLES, "requirements.txt"))


def test_unreachable_osv_says_so(monkeypatch):
    monkeypatch.setenv("MINIDEP_OSV_URL", "http://127.0.0.1:9")  # nothing listens on the discard port
    with pytest.raises(server.AuditError, match="could not reach.*internet connection"):
        server.scan(os.path.join(SAMPLES, "requirements.txt"))


def test_missing_lockfile_is_an_actionable_error(tmp_path):
    with pytest.raises(server.AuditError, match="no requirements.txt or package-lock.json"):
        server.scan(str(tmp_path))
