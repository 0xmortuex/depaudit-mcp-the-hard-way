"""Run every module's main.py for real, the way CI does.

Each main.py checks its own results with `assert` and exits non-zero on failure, so a
chapter whose code drifts out of sync with what its README claims fails here. Modules 02,
03, 05, 06 and 07 talk to the live api.osv.dev, pypi.org and registry.npmjs.org, so this needs
internet access.

Usage: python verify.py            # all modules
       python verify.py 03 06      # just these
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))


def main() -> None:
    wanted = set(sys.argv[1:])
    modules = sorted(glob.glob(os.path.join(ROOT, "[0-9][0-9]-*", "main.py")))
    failed: list[str] = []
    for path in modules:
        name = os.path.basename(os.path.dirname(path))
        if wanted and name[:2] not in wanted:
            continue
        t0 = time.time()
        # Each main.py locates its own files, so the working directory does not matter.
        proc = subprocess.run([sys.executable, path], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        status = "ok" if proc.returncode == 0 else "FAILED"
        print(f"{name:<34} {status:<6} {time.time() - t0:5.1f}s")
        if proc.returncode != 0:
            failed.append(name)
            print(proc.stdout[-1500:])
            print(proc.stderr[-1500:])
    if failed:
        sys.exit(f"failed: {', '.join(failed)}")
    print("all modules verified")


if __name__ == "__main__":
    main()
