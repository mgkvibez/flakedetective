import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from flakedetective.analyze import analyze, hypotheses
from flakedetective.failures import Failure, RunResult


def runs(spec):
    out = []
    for i, failures in enumerate(spec):
        out.append(RunResult(run_index=i, exit_code=1 if failures else 0, duration_ms=10.0,
                             failures=[Failure(test_id=t, message=m, run_index=i) for t, m in failures]))
    return out


def test_flaky_is_mixed_pass_and_fail():
    a = analyze(runs([[("t::a", "boom")], [], [("t::a", "boom")], []]))
    assert len(a.flaky) == 1
    assert a.flaky[0].score == 0.5
    assert a.flaky[0].passes == 2


def test_always_failing_is_broken_not_flaky():
    a = analyze(runs([[("t::a", "x")], [("t::a", "x")], [("t::a", "x")]]))
    assert a.flaky == []
    assert len(a.broken) == 1


def test_single_failure_in_one_run_of_ten_is_flaky_at_10_percent():
    spec = [[("t::a", "x")]] + [[]] * 9
    a = analyze(runs(spec))
    assert round(a.flaky[0].score, 2) == 0.1


def test_duplicate_failure_in_same_run_counts_once():
    a = analyze(runs([[("t::a", "x"), ("t::a", "x")], [("t::a", "x")]]))
    assert a.broken[0].fails == 2


def test_hypotheses_rank_by_evidence():
    a = analyze(runs([[("t::a", "ConnectionError")], [("t::a", "TimeoutError: timed out")],
                      [("t::a", "ConnectionError: ECONNREFUSED")], []]))
    causes = [h.cause for h in hypotheses(a.flaky[0])]
    assert causes[0] == "network"
    assert "timeout" in causes


def test_no_signal_means_no_invented_cause():
    a = analyze(runs([[("t::a", "assert 1 == 2")], []]))
    assert hypotheses(a.flaky[0]) == []
