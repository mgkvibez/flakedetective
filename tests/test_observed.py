"""A failure count is only meaningful next to what was actually observed."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from flakedetective.analyze import analyze
from flakedetective.failures import Failure, RunResult
from flakedetective.parsers import parse_passes, run_completed


def test_passes_are_parsed_for_each_harness():
    pytest_out = "tests/t.py::test_a PASSED [ 50%]\n5 passed in 0.2s\n"
    jest_out = "PASS tests/cart.test.js\n  ✓ returns total (3 ms)\nTests: 1 passed\n"
    unit_out = "test_total (tests.test_cart.CartTests) ... ok\nOK\n"
    assert parse_passes(pytest_out) == ["tests/t.py::test_a"]
    assert parse_passes(jest_out) == ["tests/cart.test.js::returns total"]
    assert parse_passes(unit_out) == ["tests.test_cart.CartTests.test_total"]


def test_a_run_without_a_summary_is_not_treated_as_complete():
    assert run_completed("FAILED tests/t.py::test_a - boom\n") is False
    assert run_completed("FAILED tests/t.py::test_a - boom\n1 failed in 0.1s\n") is True


def test_observed_runs_come_from_what_was_seen():
    runs = [
        RunResult(run_index=1, exit_code=1, duration_ms=10.0,
                  failures=[Failure(test_id="tests/t.py::test_a", message="boom", run_index=1)],
                  passes=[], complete=True),
        RunResult(run_index=2, exit_code=0, duration_ms=9.0, failures=[],
                  passes=["tests/t.py::test_a"], complete=True),
        RunResult(run_index=3, exit_code=0, duration_ms=11.0, failures=[],
                  passes=["tests/t.py::test_a"], complete=True),
    ]
    cluster = analyze(runs, parser="pytest").clusters[0]
    assert (cluster.fails, cluster.runs, cluster.passes) == (1, 3, 2)
    assert cluster.status == "flaky"
    assert cluster.passes_inferred is False
    assert abs(cluster.score - 1 / 3) < 1e-9


def test_missing_pass_lines_are_admitted_not_invented():
    runs = [
        RunResult(run_index=1, exit_code=1, duration_ms=10.0,
                  failures=[Failure(test_id="tests/t.py::test_a", message="boom", run_index=1)]),
        RunResult(run_index=2, exit_code=0, duration_ms=9.0, failures=[]),
    ]
    cluster = analyze(runs, parser="pytest").clusters[0]
    assert cluster.passes_inferred is True
    assert cluster.runs == 2
    assert cluster.passes == 1


def test_incomplete_runs_do_not_pad_the_denominator():
    runs = [
        RunResult(run_index=1, exit_code=1, duration_ms=10.0,
                  failures=[Failure(test_id="tests/t.py::test_a", message="boom", run_index=1)],
                  complete=True),
        RunResult(run_index=2, exit_code=1, duration_ms=10.0,
                  failures=[Failure(test_id="tests/t.py::test_b", message="boom", run_index=2)],
                  complete=False),
    ]
    cluster = next(c for c in analyze(runs, parser="pytest").clusters if c.test_id == "tests/t.py::test_a")
    assert cluster.runs == 1, "the fail-fast run said nothing about test_a"
