"""A local server that replays recorded OSV answers over real HTTP.

Why a server and not a mock object? Because the code under test builds URLs, sends
JSON, parses JSON and maps HTTP errors. A mock that replaces `http_json` skips all of
that. A real socket on 127.0.0.1 skips nothing and still needs no internet.

recorded.json:
    {"query": {"PyPI|requests|2.19.1": ["GHSA-..."], ...},   # package -> advisory ids
     "vulns": {"GHSA-...": {...record...}, ...}}             # id -> OSV record (trimmed)
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
RECORDED = os.path.join(HERE, "recorded.json")


class Replay:
    def __init__(self, fail_status: int = 0) -> None:
        with open(RECORDED, encoding="utf-8") as fh:
            data = json.load(fh)
        self.query: dict[str, list[str]] = data["query"]
        self.vulns: dict[str, Any] = data["vulns"]
        self.fail_status = fail_status  # answer every request with this HTTP status (0 = behave)
        self.unrecorded: list[str] = []  # questions the recording cannot answer: a test failure waiting to happen
        self.hits = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a: Any) -> None:
                pass

            def reply(self, status: int, body: Any) -> None:
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self) -> None:
                outer.hits += 1
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if outer.fail_status:
                    return self.reply(outer.fail_status, {"error": "injected"})
                results = []
                for q in body["queries"]:
                    key = f"{q['package']['ecosystem']}|{q['package']['name']}|{q['version']}"
                    if key not in outer.query:
                        outer.unrecorded.append(key)
                    ids = outer.query.get(key, [])
                    results.append({"vulns": [{"id": i} for i in ids]} if ids else {})
                self.reply(200, {"results": results})

            def do_GET(self) -> None:
                outer.hits += 1
                if outer.fail_status:
                    return self.reply(outer.fail_status, {"error": "injected"})
                vid = self.path.rsplit("/", 1)[1]
                if vid in outer.vulns:
                    self.reply(200, outer.vulns[vid])
                else:
                    outer.unrecorded.append(vid)
                    self.reply(404, {"message": "Not Found"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
