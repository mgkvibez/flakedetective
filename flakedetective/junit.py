"""Read JUnit XML into the record shape the analyzer already understands.

Every common CI can emit JUnit XML: ``pytest --junitxml``, ``jest-junit``,
``go-junit-report``, surefire. Reading it means flakedetective works on the suite
you already run in CI instead of only on suites it runs itself.

One CI run can produce several files (a matrix job, or sharded suites), so
``parse_junit_paths`` unions them into a single ``RunResult``: one run, many files.
A test that is skipped tells us nothing about flakiness, so it is recorded as
neither a pass nor a failure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, List, Sequence, Set

import xml.etree.ElementTree as ET

from .failures import Failure, RunResult

FAIL_TAGS = ("failure", "error")
SKIP_TAGS = ("skipped",)


class JunitError(ValueError):
    """A file was not JUnit XML we can read."""


def _message_of(node: ET.Element) -> str:
    for attribute in ("message", "type"):
        value = (node.get(attribute) or "").strip()
        if value:
            return value
    return (node.text or "").strip()


def _test_id(case: ET.Element) -> str:
    name = (case.get("name") or "").strip() or "(unnamed)"
    classname = (case.get("classname") or "").strip()
    return "%s::%s" % (classname, name) if classname else name


def _duration_ms(case: ET.Element) -> float:
    raw = (case.get("time") or "").strip()
    if not raw:
        return 0.0
    try:
        return round(float(raw) * 1000.0, 2)
    except ValueError:
        return 0.0


def _cases(root: ET.Element) -> Iterator[ET.Element]:
    if root.tag == "testcase":
        yield root
        return
    for case in root.iter("testcase"):
        yield case


def parse_junit_file(path: str, run_index: int = 0) -> RunResult:
    """One JUnit file as one run."""
    location = Path(path)
    try:
        root = ET.parse(str(location)).getroot()
    except (ET.ParseError, OSError) as exc:
        raise JunitError("could not read JUnit XML from %s: %s" % (location, exc)) from exc

    passes: List[str] = []
    failures: List[Failure] = []
    seen: Set[str] = set()
    total = 0
    duration = 0.0

    for case in _cases(root):
        total += 1
        duration += _duration_ms(case)
        test_id = _test_id(case)
        failure_node = next((child for child in case if child.tag in FAIL_TAGS), None)
        skipped = any(child.tag in SKIP_TAGS for child in case)

        if failure_node is not None:
            if test_id in seen:
                continue
            seen.add(test_id)
            failures.append(
                Failure(
                    test_id=test_id,
                    message=_message_of(failure_node),
                    run_index=run_index,
                    duration_ms=_duration_ms(case),
                    kind="error" if failure_node.tag == "error" else "failure",
                )
            )
        elif skipped:
            continue
        else:
            if test_id in seen:
                continue
            seen.add(test_id)
            passes.append(test_id)

    return RunResult(
        run_index=run_index,
        exit_code=1 if failures else 0,
        duration_ms=round(duration, 2),
        failures=failures,
        passes=passes,
        complete=total > 0,
        output_path=str(location),
    )


def parse_junit_paths(paths: Sequence[str], run_index: int = 0) -> RunResult:
    """Several JUnit files as one run: a matrix job or sharded suite is still one run."""
    if not paths:
        raise JunitError("no JUnit files given")

    merged = RunResult(run_index=run_index, exit_code=0, duration_ms=0.0)
    failed_ids = set()
    passed_ids = set()
    any_complete = False

    for path in paths:
        result = parse_junit_file(path, run_index)
        merged.duration_ms = round(merged.duration_ms + result.duration_ms, 2)
        any_complete = any_complete or result.complete
        for failure in result.failures:
            if failure.test_id in failed_ids or failure.test_id in passed_ids:
                continue
            failed_ids.add(failure.test_id)
            merged.failures.append(failure)
        for test_id in result.passes:
            if test_id in passed_ids or test_id in failed_ids:
                continue
            passed_ids.add(test_id)
            merged.passes.append(test_id)
        merged.output_path = (
            result.output_path if not merged.output_path
            else merged.output_path + "," + result.output_path
        )

    merged.exit_code = 1 if merged.failures else 0
    merged.complete = any_complete
    return merged
