"""What a human reads after a run."""

from __future__ import annotations

import json
from typing import List, Optional

from .analyze import Analysis, Cluster, hypotheses
from . import quarantine

BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def _bar(score: float, width: int = 12) -> str:
    filled = int(round(score * width))
    return "[" + "#" * filled + "." * (width - filled) + "]"


def repro_command(cluster: Cluster, parser: str) -> str:
    tid = cluster.test_id
    if parser == "jest":
        name = tid.split("::", 1)[1] if "::" in tid else tid
        return 'jest -t "{}" --runInBand'.format(name)
    if parser == "unittest":
        return "python -m unittest {} ; for i in 1 2 3 4 5; do python -m unittest {} || true; done".format(tid, tid)
    return 'for i in 1 2 3 4 5; do pytest "{}" -q || echo "FAILED on attempt $i"; done'.format(tid)


def render_text(analysis: Analysis, top: int = 10, color: bool = True) -> str:
    b, d, r, y, z = (BOLD, DIM, RED, YELLOW, RESET) if color else ("", "", "", "", "")
    lines: List[str] = []
    flaky = analysis.flaky
    broken = analysis.broken
    lines.append("{}flakedetective{}: {} run(s), {} flaky, {} always-failing".format(
        b, z, analysis.total_runs, len(flaky), len(broken)))

    if not flaky and not broken:
        lines.append("")
        lines.append("Every test that failed, failed every time. Nothing is flaky.")
        return "\n".join(lines)

    if flaky:
        lines.append("")
        lines.append("{}Flaky (passed and failed){}".format(b, z))
        for c in flaky[:top]:
            colour = r if c.score >= 0.5 else y
            lines.append("  {}{} {} {}/{} runs{}  {}".format(
                colour, _bar(c.score), "{:.0%}".format(c.score), c.fails, c.runs, z, c.test_id
                + ("  (runs assumed: no pass lines in output)" if getattr(c, "passes_inferred", False) else "")))
            for h in hypotheses(c)[:1]:
                lines.append("     {}likely {}: {}{}".format(d, h.cause, h.suggestion, z))
            lines.append("     {}prove it: {}{}".format(d, repro_command(c, analysis.parser), z))
        if len(flaky) > top:
            lines.append("  {}... and {} more{}".format(d, len(flaky) - top, z))

    if broken:
        lines.append("")
        lines.append("{}Always failing (not flaky, just broken){}".format(b, z))
        for c in broken[:top]:
            lines.append("  {}/{} runs  {}".format(c.fails, c.runs, c.test_id))

    if flaky:
        lines.append("")
        lines.append("{}Quarantine (copy, then fix one per PR):{}".format(b, z))
        lines.append(quarantine.emit([c.test_id for c in flaky[:top]], fmt="pytest" if analysis.parser != "jest" else "jest"))
    lines.append("")
    lines.append("{}A flaky test is a fact (it both passed and failed). A cause is a hypothesis from the failure text until you reproduce it.{}".format(d, z))
    return "\n".join(lines)


def render_json(analysis: Analysis) -> str:
    payload = {
        "total_runs": analysis.total_runs,
        "parser": analysis.parser,
        "flaky": [
            {"test": c.test_id, "score": round(c.score, 3), "fails": c.fails, "runs": c.runs,
             "passes_inferred": bool(getattr(c, "passes_inferred", False)),
             "likely_causes": [{"cause": h.cause, "evidence": h.evidence, "suggestion": h.suggestion}
                               for h in hypotheses(c)],
             "repro": repro_command(c, analysis.parser)}
            for c in analysis.flaky
        ],
        "broken": [{"test": c.test_id, "fails": c.fails, "runs": c.runs} for c in analysis.broken],
    }
    return json.dumps(payload, indent=2)
