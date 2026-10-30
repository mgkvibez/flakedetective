import shutil, sys, pathlib, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from flakedetective.runner import run_once, run_suite, load_results, ledger_path

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "flaky_suite.py"


def isolated_suite(tmp):
    """Copy the fixture somewhere clean so its attempt counter starts at zero."""
    dest = pathlib.Path(tmp) / "suite.py"
    shutil.copy(FIXTURE, dest)
    counter = dest.with_name(".counter")
    if counter.exists():
        counter.unlink()
    return dest


def test_run_once_parses_failures():
    with tempfile.TemporaryDirectory() as tmp:
        suite = isolated_suite(tmp)
        result = run_once([sys.executable, str(suite)], 0)
        assert result.exit_code == 1
        ids = {f.test_id for f in result.failures}
        assert "tests/test_auth.py::test_login" in ids


def test_run_suite_writes_a_ledger_that_round_trips():
    with tempfile.TemporaryDirectory() as tmp:
        suite = isolated_suite(tmp)
        results = run_suite([sys.executable, str(suite)], runs=3, state_dir=str(pathlib.Path(tmp) / ".flakedetective"))
        assert len(results) == 3
        assert ledger_path(str(pathlib.Path(tmp) / ".flakedetective")).exists()
        loaded = load_results(str(pathlib.Path(tmp) / ".flakedetective" / "runs.jsonl"))
        assert [r.run_index for r in loaded] == [0, 1, 2]
        assert sum(1 for r in loaded if any("test_total" in f.test_id for f in r.failures)) >= 1


def test_timeout_is_recorded_as_a_suite_failure():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_once([sys.executable, "-c", "import time; time.sleep(5)"], 0, timeout=0.2)
        assert result.exit_code == 124
        assert result.failures and result.failures[0].test_id == "<suite>"


def test_missing_ledger_loads_empty():
    with tempfile.TemporaryDirectory() as tmp:
        assert load_results(str(pathlib.Path(tmp) / "nope.jsonl")) == []
