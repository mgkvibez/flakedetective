import json, shutil, sys, pathlib, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from flakedetective.cli import main, EXIT_CLEAN, EXIT_FLAKY, EXIT_USAGE

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "flaky_suite.py"


def setup_suite(tmp):
    dest = pathlib.Path(tmp) / "suite.py"
    shutil.copy(FIXTURE, dest)
    return dest


def test_run_finds_flaky_and_exits_three(tmp_path, capsys):
    suite = setup_suite(tmp_path)
    code = main(["run", "--runs", "4", "--no-color", "--cwd", str(tmp_path), "--",
                 sys.executable, "suite.py"])
    out = capsys.readouterr().out
    assert code == EXIT_FLAKY
    assert "test_total" in out
    assert "always-failing" in out


def test_run_without_command_is_usage_error(capsys):
    assert main(["run", "--runs", "2"]) == EXIT_USAGE
    assert "after --" in capsys.readouterr().err


def test_json_flag_is_machine_readable(tmp_path, capsys):
    setup_suite(tmp_path)
    main(["run", "--runs", "3", "--json", "--cwd", str(tmp_path), "--", sys.executable, "suite.py"])
    data = json.loads(capsys.readouterr().out)
    assert data["total_runs"] == 3
    assert isinstance(data["flaky"], list)


def test_quarantine_subcommand_prints_a_snippet(tmp_path, capsys):
    setup_suite(tmp_path)
    main(["run", "--runs", "3", "--no-color", "--cwd", str(tmp_path), "--", sys.executable, "suite.py"])
    capsys.readouterr()
    code = main(["quarantine", str(pathlib.Path(tmp_path) / ".flakedetective" / "runs.jsonl")])
    out = capsys.readouterr().out
    assert code == EXIT_CLEAN
    assert "--deselect=" in out


def test_analyze_without_ledger_is_usage_error(tmp_path, capsys):
    assert main(["analyze", str(tmp_path / "missing.jsonl")]) == EXIT_USAGE
