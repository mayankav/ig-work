#!/usr/bin/env python3
"""Run both suite styles; expected error text must not become CI annotations."""
import json
import os
from pathlib import Path
import subprocess
import sys


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    logs = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / ("suresilly-tests-" + str(os.getpid()))
    logs.mkdir()
    failed = []
    for path in sorted((root / ".agents/skills/suresilly-carousel/tests").glob("test_*.py")):
        pytest_style = any(line.startswith(("import pytest", "from pytest"))
                           for line in path.read_text().splitlines())
        cmd = [sys.executable] + (["-m", "pytest", str(path), "-q"] if pytest_style else [str(path)])
        result = subprocess.run(cmd, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (logs / (path.stem + ".log")).write_text(result.stdout)
        print(f"{'FAIL' if result.returncode else 'PASS'} {path.name}", flush=True)
        if result.returncode:
            failed.append(path.name)
            # Prefix every line: even an intentional ::error:: is now plain text.
            for line in result.stdout.splitlines()[-30:]:
                print("  | " + line)
    if failed:
        reason = "Failed tests: " + ", ".join(failed)
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a") as handle:
                handle.write("reason=" + reason + "\n")
        print(reason)
    print(f"Full test logs: {logs}")
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
