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
    """Pick a parser from the output's own voice."""
    if re.search(r"^FAILED\s+\S+::", output, re.M) or re.search(r"^\d+ (?:passed|failed)", output, re.M):
        return "pytest"
    if re.search(r"^\s*(?:✕|×|✗)\s+\S+.*\(\d+\s*ms\)", output, re.M) or re.search(r"^Tests:.*failed", output, re.M):
        return "jest"
    if re.search(r"^(?:FAIL|ERROR):\s+\w+\s+\(", output, re.M):
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
