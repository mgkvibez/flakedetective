"""Turn runner output into Failure objects.

Each harness gets one function and one entry in PARSERS. Adding a harness means
adding a function and a fixture, nothing else.
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional

from .failures import Failure

# pytest: "FAILED tests/test_cart.py::test_total - AssertionError: assert 3 == 4"
PYTEST_FAILED = re.compile(r"^(?P<kind>FAILED|ERROR)\s+(?P<id>[^\s]+)(?:\s+-\s+(?P<msg>.*))?$")
# pytest short summary can also be "tests/test_cart.py::test_total F" for -v runs
PYTEST_INLINE = re.compile(r"^(?P<id>[\w./\\-]+\.py::[\w\[\]\-\.]+)\s+(?P<mark>FAILED|ERROR)\b(?:\s+(?P<msg>.*))?$")
# unittest: "FAIL: test_total (tests.test_cart.CartTests)"
UNITTEST_FAILED = re.compile(r"^(?P<kind>FAIL|ERROR):\s+(?P<name>\w+)\s+\((?P<cls>[\w.]+)\)")
# jest: "  ✕ returns total (12 ms)"
JEST_FAILED = re.compile(r"^\s*(?P<mark>✕|×|✗)\s+(?P<name>[^(]+?)\s*\((?P<ms>\d+)\s*ms\)")
# jest suite line: "FAIL tests/cart.test.js"
JEST_SUITE = re.compile(r"^FAIL\s+(?P<path>\S+\.(?:js|jsx|ts|tsx))")


def parse_pytest(output: str, run_index: int = 0) -> List[Failure]:
    failures: List[Failure] = []
    current_message: Dict[str, str] = {}
    for raw in output.splitlines():
        line = raw.rstrip()
        m = PYTEST_FAILED.match(line.strip())
        if m:
            failures.append(Failure(
                test_id=m.group("id"),
                message=(m.group("msg") or "").strip(),
                run_index=run_index,
                kind="error" if m.group("kind") == "ERROR" else "failure",
            ))
            continue
        m = PYTEST_INLINE.match(line.strip())
        if m:
            failures.append(Failure(
                test_id=m.group("id"),
                message=(m.group("msg") or "").strip(),
                run_index=run_index,
                kind="error" if m.group("mark") == "ERROR" else "failure",
            ))
            continue
        # "E   AssertionError: assert 3 == 4" belongs to the most recent failure
        stripped = line.strip()
        if stripped.startswith("E ") and failures and not failures[-1].message:
            failures[-1].message = stripped[2:].strip()
    return failures


def parse_jest(output: str, run_index: int = 0) -> List[Failure]:
    failures: List[Failure] = []
    suite = ""
    for raw in output.splitlines():
        line = raw.rstrip()
        ms = JEST_SUITE.match(line.strip())
        if ms:
            suite = ms.group("path")
            continue
        m = JEST_FAILED.match(line)
        if m:
            test_id = "{}::{}".format(suite or "jest", m.group("name").strip())
            failures.append(Failure(
                test_id=test_id,
                message="",
                run_index=run_index,
                duration_ms=float(m.group("ms")),
            ))
    return failures


def parse_unittest(output: str, run_index: int = 0) -> List[Failure]:
    failures: List[Failure] = []
    for raw in output.splitlines():
        line = raw.strip()
        m = UNITTEST_FAILED.match(line)
        if m:
            failures.append(Failure(
                test_id="{}.{}".format(m.group("cls"), m.group("name")),
                message="",
                run_index=run_index,
                kind="error" if m.group("kind") == "ERROR" else "failure",
            ))
            continue
        # "AssertionError: 3 != 4" lines follow the FAIL header
        if failures and not failures[-1].message and re.match(r"^[A-Za-z_]*Error\b", line):
            failures[-1].message = line[:200]
    return failures


def detect(output: str) -> str:
    """Pick a parser from the output's own voice.

    Detection must work on green runs too: a suite that passed everything still
    names its passes, and those names are the denominator, so only reading the
    failure-shaped markers would throw that evidence away.
    """
    if re.search(r"^FAILED\s+\S+::", output, re.M) or re.search(r"^\d+ (?:passed|failed|error)", output, re.M):
        return "pytest"
    if (re.search(r"^\s*(?:PASS|FAIL)\s+\S+", output, re.M)
            or re.search(r"^\s*(?:✓|×|✕|✗)\s+\S+", output, re.M)
            or re.search(r"^Tests:\s", output, re.M)):
        return "jest"
    if (re.search(r"^(?:FAIL|ERROR):\s+\w+\s+\(", output, re.M)
            or re.search(r"\.\.\.\s*ok\b", output, re.M)
            or re.search(r"^Ran \d+ tests? in", output, re.M)
            or re.search(r"^OK\b", output, re.M)):
        return "unittest"
    return "pytest"


PARSERS: Dict[str, Callable[[str, int], List[Failure]]] = {
    "pytest": parse_pytest,
    "jest": parse_jest,
    "unittest": parse_unittest,
}


def parse(output: str, parser: str = "auto", run_index: int = 0) -> List[Failure]:
    if parser == "auto":
        parser = detect(output)
    fn = PARSERS.get(parser)
    if fn is None:
        raise ValueError("unknown parser {!r}; choose from {}".format(parser, ", ".join(sorted(PARSERS))))
    return fn(output, run_index)


PYTEST_PASS = re.compile(r"^(?P<test>[\w./-]+\.py::[\w:.\[\]-]+)\s+PASSED")
JEST_FILE = re.compile(r"^\s*(?:PASS|FAIL)\s+(?P<file>\S+)")
JEST_PASS = re.compile(r"^\s*[\u2713\u221a]\s+(?P<name>.+?)(?:\s+\(\d+\s*m[sx]\))?\s*$")
UNITTEST_PASS = re.compile(r"^(?P<name>\w+) \((?P<cls>[\w.]+)\)\s*\.\.\.\s*ok\b")
PYTEST_SUMMARY = re.compile(r"\b\d+ (?:passed|failed|error)")
JEST_SUMMARY = re.compile(r"^\s*Tests:\s")
UNITTEST_SUMMARY = re.compile(r"^(?:OK|FAILED)\b")


def parse_passes(output: str, parser: str = "auto") -> List[str]:
    """Test ids that the harness reported as passing, in order.

    Only verbose-ish output names its passes. When a harness prints no pass
    lines this returns an empty list, and the caller has to say so instead of
    inventing a count.
    """
    name = detect(output) if parser == "auto" else parser
    found: List[str] = []
    current = ""
    for line in output.splitlines():
        if name == "pytest":
            m = PYTEST_PASS.match(line)
            if m:
                found.append(m.group("test"))
        elif name == "jest":
            f = JEST_FILE.match(line)
            if f:
                current = f.group("file")
            m = JEST_PASS.match(line)
            if m:
                found.append("{}::{}".format(current, m.group("name").strip()) if current else m.group("name").strip())
        elif name == "unittest":
            m = UNITTEST_PASS.match(line)
            if m:
                found.append("{}.{}".format(m.group("cls"), m.group("name")))
    return found


def run_completed(output: str, parser: str = "auto") -> bool:
    """Did the harness get far enough to print its own summary?

    A suite killed by fail-fast or a timeout prints no summary, and its silence
    about every later test is not evidence that they passed.
    """
    name = detect(output) if parser == "auto" else parser
    text = output
    if name == "pytest":
        return bool(PYTEST_SUMMARY.search(text) or "no tests ran" in text.lower())
    if name == "jest":
        return bool(JEST_SUMMARY.search(text))
    if name == "unittest":
        return bool(UNITTEST_SUMMARY.search(text, ))
    return True
