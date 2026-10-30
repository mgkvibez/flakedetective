import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from flakedetective.analyze import analyze
from flakedetective.failures import Failure, RunResult
from flakedetective.report import render_text, render_json, repro_command


def sample():
    runs = []
    for i, fails in enumerate([[("tests/a.py::test_x", "ConnectionError")], [], [("tests/a.py::test_x", "ConnectionError")], []]):
        runs.append(RunResult(run_index=i, exit_code=1 if fails else 0, duration_ms=10.0,
                              failures=[Failure(test_id=t, message=m, run_index=i) for t, m in fails]))
    return analyze(runs, parser="pytest")


def test_text_report_shows_score_cause_and_repro():
    out = render_text(sample(), color=False)
    assert "50%" in out
    assert "tests/a.py::test_x" in out
    assert "network" in out
    assert "prove it" in out
    assert "\033[" not in out


def test_text_report_quarantines_flaky_tests():
    out = render_text(sample(), color=False)
    assert "--deselect=tests/a.py::test_x" in out


def test_json_report_is_parseable():
    data = json.loads(render_json(sample()))
    assert data["flaky"][0]["test"] == "tests/a.py::test_x"
    assert data["flaky"][0]["score"] == 0.5
    assert data["flaky"][0]["likely_causes"][0]["cause"] == "network"


def test_repro_command_per_harness():
    s = sample()
    assert repro_command(s.flaky[0], "jest").startswith('jest -t "')
    assert "unittest" in repro_command(s.flaky[0], "unittest")


def test_clean_run_says_so_plainly():
    clean = analyze([RunResult(0, 0, 5.0, []), RunResult(1, 0, 5.0, [])], parser="pytest")
    assert "Nothing is flaky" in render_text(clean, color=False)
