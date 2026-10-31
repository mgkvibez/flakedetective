"""Entry point for the composite GitHub Action.

action.yml stays a thin shell on purpose: everything here takes its environment as
an argument, so the whole Action can be tested on a laptop with no GitHub and no
network. The Action reads the JUnit XML your CI already produced, appends it to the
ledger, prints a job summary, and sets step outputs.

Inputs, all optional except the JUnit location:

===========================  =====================================================
FLAKEDETECTIVE_JUNIT         file, glob, or comma/space separated list of them
FLAKEDETECTIVE_STATE_DIR     where runs.jsonl lives; cache this between runs
FLAKEDETECTIVE_THRESHOLD     minimum flake score to report, default 0.0
FLAKEDETECTIVE_FAIL_ON_FLAKY "true" to fail the step when anything is flagged
===========================  =====================================================
"""

from __future__ import annotations

import glob
import json
import os
import sys
from typing import Dict, List, Optional, Sequence

from .analyze import Analysis, analyze, hypotheses
from .junit import JunitError, parse_junit_paths
from .quarantine import emit
from .report import render_text
from .runner import STATE_DIR, append_results, ledger_path, load_results

FLAG_FILENAME = "flakedetective.txt"


def resolve_paths(spec: str, root: str = ".") -> List[str]:
    """Turn a spec of files, globs, and comma/space separated entries into real files."""
    found: List[str] = []
    for chunk in (spec or "").replace(",", "\n").split():
        pattern = chunk if os.path.isabs(chunk) else os.path.join(root, chunk)
        matches = sorted(glob.glob(pattern, recursive=True))
        if not matches and os.path.isfile(pattern):
            matches = [pattern]
        for match in matches:
            if os.path.isfile(match) and match not in found:
                found.append(match)
    return found


def next_run_index(state_dir: str = STATE_DIR) -> int:
    """Continue the ledger's numbering so every ingest is a distinct run."""
    path = ledger_path(state_dir)
    if not path.exists():
        return 0
    highest = -1
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            highest = max(highest, int(json.loads(line).get("run_index", -1)))
        except (ValueError, TypeError, AttributeError):
            continue
    return highest + 1


def ingest_junit(spec: str, state_dir: str = STATE_DIR, root: str = ".") -> Dict[str, object]:
    """Parse every matching JUnit file as ONE run and append it to the ledger."""
    paths = resolve_paths(spec, root)
    if not paths:
        raise JunitError("no JUnit XML matched %r" % (spec or "(empty input)"))
    result = parse_junit_paths(paths, run_index=next_run_index(state_dir))
    append_results([result], state_dir=state_dir)
    return {
        "files": paths,
        "tests": len(result.passes) + len(result.failures),
        "failures": len(result.failures),
        "run_index": result.run_index,
    }


def flagged(analysis: Analysis, threshold: float) -> list:
    return [cluster for cluster in analysis.flaky if cluster.score >= threshold]


def render_summary(analysis: Analysis, rows: Sequence, threshold: float, top: int = 20) -> str:
    """The job summary, written with the same numbers the CLI prints."""
    out = ["## Flakedetective", ""]
    out.append(
        "%d run(s) in history, %d flaky test(s), %d failing consistently."
        % (analysis.total_runs, len(analysis.flaky), len(analysis.broken))
    )
    if threshold:
        out.append("")
        out.append("Only scores at or above %.2f are listed below." % threshold)
    out.append("")
    if rows:
        out.append("| test | flake score | failed / seen | likely cause |")
        out.append("| --- | --- | --- | --- |")
        for cluster in rows[:max(1, top)]:
            causes = hypotheses(cluster)
            cause = causes[0].cause if causes else "unclassified"
            out.append(
                "| `%s` | %.2f | %d / %d | %s |"
                % (cluster.test_id, cluster.score, cluster.fails, cluster.runs, cause)
            )
        out.append("")
        out.append("<details><summary>Quarantine snippet</summary>")
        out.append("")
        out.append("```")
        out.append(emit([cluster.test_id for cluster in rows]))
        out.append("```")
        out.append("")
        out.append("</details>")
    else:
        out.append("Nothing above the threshold. Either the suite is steady or the history is short.")
    return "\n".join(out)


def decide_exit(rows: Sequence, fail_on_flaky: bool) -> int:
    return 1 if (rows and fail_on_flaky) else 0


def _write(handle_path: Optional[str], text: str) -> None:
    if not handle_path:
        return
    with open(handle_path, "a", encoding="utf-8") as handle:
        handle.write(text if text.endswith("\n") else text + "\n")


def main(env: Optional[Dict[str, str]] = None) -> int:
    env = dict(os.environ if env is None else env)
    spec = env.get("FLAKEDETECTIVE_JUNIT", "")
    state_dir = env.get("FLAKEDETECTIVE_STATE_DIR") or STATE_DIR
    root = env.get("GITHUB_WORKSPACE") or "."
    try:
        threshold = float(env.get("FLAKEDETECTIVE_THRESHOLD") or 0.0)
    except ValueError:
        print("flakedetective: threshold must be a number", file=sys.stderr)
        return 2
    fail_on_flaky = (env.get("FLAKEDETECTIVE_FAIL_ON_FLAKY") or "").strip().lower() in (
        "1", "true", "yes",
    )
    try:
        top = int(env.get("FLAKEDETECTIVE_TOP") or 20)
    except ValueError:
        top = 20

    try:
        ingested = ingest_junit(spec, state_dir=state_dir, root=root)
    except JunitError as exc:
        print("flakedetective: %s" % exc, file=sys.stderr)
        return 2

    analysis = analyze(load_results(state_dir=state_dir))
    rows = flagged(analysis, threshold)
    summary = render_summary(analysis, rows, threshold, top=top)
    _write(env.get("GITHUB_STEP_SUMMARY"), summary)
    if not env.get("GITHUB_STEP_SUMMARY"):
        print(summary)
        print(render_text(analysis, color=False))

    _write(env.get("GITHUB_OUTPUT"), "flaky-count=%d" % len(rows))
    _write(env.get("GITHUB_OUTPUT"), "quarantine=%s" % ",".join(c.test_id for c in rows))
    _write(os.path.join(state_dir, FLAG_FILENAME), "\n".join(c.test_id for c in rows))

    print(
        "flakedetective: ingested %d test(s) from %d file(s); %d flaky above threshold"
        % (ingested["tests"], len(ingested["files"]), len(rows)),
        file=sys.stderr,
    )
    return decide_exit(rows, fail_on_flaky)


if __name__ == "__main__":
    raise SystemExit(main())
