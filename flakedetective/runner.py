"""Run a suite N times and keep every observation.

Nothing here is clever: run it, capture both streams, parse the failures, and
append the run to a JSONL ledger so later analysis needs no re-run.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Sequence

from .failures import Failure, RunResult
from .parsers import parse

STATE_DIR = ".flakedetective"
LEDGER = "runs.jsonl"


def run_once(command: Sequence[str], run_index: int, timeout: Optional[float] = None,
             cwd: Optional[str] = None, parser: str = "auto") -> RunResult:
    started = time.monotonic()
    try:
        proc = subprocess.run(list(command), capture_output=True, text=True,
                              timeout=timeout, cwd=cwd, errors="replace")
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        partial = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        partial_err = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        output = partial + "\n" + partial_err + "\nTIMEOUT after {}s".format(timeout)
        code = 124
    duration_ms = (time.monotonic() - started) * 1000.0
    failures = parse(output, parser=parser, run_index=run_index)
    if code != 0 and not failures:
        failures = [Failure(test_id="<suite>", message="suite exited {} with no parseable failure".format(code),
                            run_index=run_index)]
    return RunResult(run_index=run_index, exit_code=code, duration_ms=duration_ms, failures=failures)


def run_suite(command: Sequence[str], runs: int = 10, timeout: Optional[float] = None,
              cwd: Optional[str] = None, parser: str = "auto",
              state_dir: str = STATE_DIR) -> List[RunResult]:
    results: List[RunResult] = []
    for i in range(runs):
        results.append(run_once(command, i, timeout=timeout, cwd=cwd, parser=parser))
    append_results(results, state_dir=state_dir)
    return results


def ledger_path(state_dir: str = STATE_DIR) -> Path:
    return Path(state_dir) / LEDGER


def append_results(results: Sequence[RunResult], state_dir: str = STATE_DIR) -> Path:
    path = ledger_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps({
                "run_index": r.run_index,
                "exit_code": r.exit_code,
                "duration_ms": round(r.duration_ms, 2),
                "failures": [{"id": f.test_id, "message": f.message, "kind": f.kind,
                              "duration_ms": f.duration_ms} for f in r.failures],
            }) + "\n")
    return path


def load_results(path: Optional[str] = None, state_dir: str = STATE_DIR) -> List[RunResult]:
    p = Path(path) if path else ledger_path(state_dir)
    if not p.exists():
        return []
    out: List[RunResult] = []
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            out.append(RunResult(
                run_index=d.get("run_index", 0),
                exit_code=d.get("exit_code", 0),
                duration_ms=d.get("duration_ms", 0.0),
                failures=[Failure(test_id=f.get("id", ""), message=f.get("message", ""),
                                  kind=f.get("kind", "failure"), duration_ms=f.get("duration_ms", 0.0),
                                  run_index=d.get("run_index", 0)) for f in d.get("failures", [])],
            ))
    return out
