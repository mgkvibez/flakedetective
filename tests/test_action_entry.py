"""The Action's entry point, tested with no GitHub and no network."""

from __future__ import annotations

import os

from flakedetective import action_entry
from flakedetective.action_entry import (
    decide_exit,
    flagged,
    ingest_junit,
    main,
    next_run_index,
    render_summary,
    resolve_paths,
)
from flakedetective.analyze import analyze
from flakedetective.runner import load_results


def junit(tmp_path, name, failures=(), passes=()):
    cases = "".join('<testcase classname="m" name="%s" time="0.1"/>' % p for p in passes)
    for f in failures:
        cases += (
            '<testcase classname="m" name="%s" time="0.1">'
            '<failure message="boom"/></testcase>' % f
        )
    path = tmp_path / name
    path.write_text("<testsuite>%s</testsuite>" % cases, encoding="utf-8")
    return str(path)


def test_resolve_paths_accepts_globs_and_lists(tmp_path):
    first = junit(tmp_path, "a.xml", passes=["x"])
    second = junit(tmp_path, "b.xml", passes=["y"])
    assert resolve_paths(os.path.join(str(tmp_path), "*.xml")) == sorted([first, second])
    assert resolve_paths("%s,%s" % (first, second)) == [first, second]


def test_resolve_paths_reports_nothing_when_nothing_matches(tmp_path):
    assert resolve_paths(os.path.join(str(tmp_path), "*.nope")) == []


def test_run_index_starts_at_zero_and_increments(tmp_path):
    state = str(tmp_path / "state")
    assert next_run_index(state) == 0
    path = junit(tmp_path, "a.xml", passes=["x"])
    ingest_junit(path, state_dir=state)
    assert next_run_index(state) == 1


def test_ingest_writes_exactly_one_run(tmp_path):
    state = str(tmp_path / "state")
    path = junit(tmp_path, "a.xml", passes=["ok"], failures=["bad"])
    info = ingest_junit(path, state_dir=state)
    assert info["tests"] == 2 and info["failures"] == 1 and info["run_index"] == 0
    ledger = load_results(state_dir=state)
    assert len(ledger) == 1
    assert ledger[0].failures[0].test_id == "m::bad"


def test_no_matching_files_is_an_error_not_an_empty_run(tmp_path):
    import pytest
    from flakedetective.junit import JunitError

    with pytest.raises(JunitError):
        ingest_junit(str(tmp_path / "*.missing"), state_dir=str(tmp_path / "state"))


def test_threshold_filters_rows(tmp_path):
    state = str(tmp_path / "state")
    ingest_junit(junit(tmp_path, "a.xml", passes=["steady", "wobbly"]), state_dir=state)
    ingest_junit(junit(tmp_path, "b.xml", failures=["wobbly"], passes=["steady"]), state_dir=state)
    analysis = analyze(load_results(state_dir=state))
    assert [c.test_id for c in flagged(analysis, 0.5)] == ["m::wobbly"]
    assert flagged(analysis, 0.0)[0].test_id == "m::wobbly"


def test_summary_names_the_test_and_carries_the_snippet(tmp_path):
    state = str(tmp_path / "state")
    ingest_junit(junit(tmp_path, "a.xml", passes=["wobbly"]), state_dir=state)
    ingest_junit(junit(tmp_path, "b.xml", failures=["wobbly"]), state_dir=state)
    analysis = analyze(load_results(state_dir=state))
    rows = flagged(analysis, 0.0)
    summary = render_summary(analysis, rows, 0.0)
    assert "m::wobbly" in summary
    assert "flake score" in summary
    assert "Quarantine snippet" in summary
    assert "2 run(s) in history" in summary


def test_summary_is_honest_when_nothing_is_flagged(tmp_path):
    state = str(tmp_path / "state")
    ingest_junit(junit(tmp_path, "a.xml", passes=["steady"]), state_dir=state)
    analysis = analyze(load_results(state_dir=state))
    summary = render_summary(analysis, flagged(analysis, 0.0), 0.0)
    assert "Nothing above the threshold" in summary


def test_decide_exit_only_fails_when_asked():
    rows = [object()]
    assert decide_exit(rows, False) == 0
    assert decide_exit(rows, True) == 1
    assert decide_exit([], True) == 0



def seed_flaky(tmp_path, state, summary_path, *names):
    """A test is only flaky if it both passed and failed, so seed one of each."""
    base = {
        "FLAKEDETECTIVE_STATE_DIR": state,
        "GITHUB_STEP_SUMMARY": str(summary_path),
        "GITHUB_WORKSPACE": str(tmp_path),
    }
    main(dict(base, FLAKEDETECTIVE_JUNIT=junit(tmp_path, "seed_pass.xml", passes=list(names))))
    return base

def test_main_writes_summary_and_outputs(tmp_path):
    state = str(tmp_path / "state")
    summary_path = tmp_path / "summary.md"
    output_path = tmp_path / "out.txt"
    seed_flaky(tmp_path, state, summary_path, "wobbly")
    env = {
        "FLAKEDETECTIVE_JUNIT": junit(tmp_path, "now.xml", failures=["wobbly"]),
        "FLAKEDETECTIVE_STATE_DIR": state,
        "GITHUB_STEP_SUMMARY": str(summary_path),
        "GITHUB_OUTPUT": str(output_path),
        "GITHUB_WORKSPACE": str(tmp_path),
    }
    assert main(env) == 0
    assert "flake score" in summary_path.read_text()
    outputs = output_path.read_text()
    assert "flaky-count=" in outputs


def test_main_fails_the_step_when_asked(tmp_path):
    state = str(tmp_path / "state")
    seed_flaky(tmp_path, state, tmp_path / "summary.md", "bad")
    env = {
        "FLAKEDETECTIVE_JUNIT": junit(tmp_path, "now.xml", failures=["bad"]),
        "FLAKEDETECTIVE_STATE_DIR": state,
        "FLAKEDETECTIVE_FAIL_ON_FLAKY": "true",
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
        "GITHUB_WORKSPACE": str(tmp_path),
    }
    assert main(env) == 1


def test_main_returns_usage_error_when_no_junit_matched(tmp_path):
    env = {
        "FLAKEDETECTIVE_JUNIT": os.path.join(str(tmp_path), "*.none"),
        "FLAKEDETECTIVE_STATE_DIR": str(tmp_path / "state"),
        "GITHUB_WORKSPACE": str(tmp_path),
    }
    assert main(env) == 2


def test_cross_run_history_accumulates_and_surfaces_a_flake(tmp_path):
    """The whole point: one run alone cannot show a flake, the ledger can."""
    state = str(tmp_path / "state")
    summary_path = tmp_path / "summary.md"
    base = {
        "FLAKEDETECTIVE_STATE_DIR": state,
        "GITHUB_STEP_SUMMARY": str(summary_path),
        "GITHUB_WORKSPACE": str(tmp_path),
    }
    main(dict(base, FLAKEDETECTIVE_JUNIT=junit(tmp_path, "run1.xml", passes=["wobbly"])))
    main(dict(base, FLAKEDETECTIVE_JUNIT=junit(tmp_path, "run2.xml", failures=["wobbly"])))

    ledger = load_results(state_dir=state)
    assert [r.run_index for r in ledger] == [0, 1]
    analysis = analyze(ledger)
    assert analysis.total_runs == 2
    assert [c.test_id for c in analysis.flaky] == ["m::wobbly"]
    assert "m::wobbly" in summary_path.read_text()


def test_outputs_file_is_valid_key_value_lines(tmp_path):
    state = str(tmp_path / "state")
    output_path = tmp_path / "out.txt"
    seed_flaky(tmp_path, state, tmp_path / "summary.md", "one", "two")
    env = {
        "FLAKEDETECTIVE_JUNIT": junit(tmp_path, "now.xml", failures=["one", "two"]),
        "FLAKEDETECTIVE_STATE_DIR": state,
        "GITHUB_OUTPUT": str(output_path),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
        "GITHUB_WORKSPACE": str(tmp_path),
    }
    main(env)
    pairs = dict(line.split("=", 1) for line in output_path.read_text().splitlines() if "=" in line)
    assert pairs["flaky-count"] == "2"
    assert set(pairs["quarantine"].split(",")) == {"m::one", "m::two"}


def test_the_flag_file_records_what_was_quarantined(tmp_path):
    state = str(tmp_path / "state")
    seed_flaky(tmp_path, state, tmp_path / "summary.md", "flagged")
    env = {
        "FLAKEDETECTIVE_JUNIT": junit(tmp_path, "now.xml", failures=["flagged"]),
        "FLAKEDETECTIVE_STATE_DIR": state,
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
        "GITHUB_WORKSPACE": str(tmp_path),
    }
    main(env)
    flag = (tmp_path / "state" / action_entry.FLAG_FILENAME).read_text()
    assert flag.strip() == "m::flagged"
