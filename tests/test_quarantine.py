import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
from flakedetective import quarantine


def test_pytest_snippet_deselects_exact_tests():
    out = quarantine.emit(["tests/a.py::test_x", "tests/b.py::test_y"], "pytest", ratio=0.5)
    assert '--deselect=tests/a.py::test_x' in out
    assert '--deselect=tests/b.py::test_y' in out
    assert "50%" in out


def test_jest_snippet_scopes_to_files_and_is_honest():
    out = quarantine.emit(["tests/a.test.js::does a thing"], "jest")
    assert "testPathIgnorePatterns" in out
    assert "test.skip('does a thing'" in out
    assert "no per-test config" in out


def test_unknown_format_raises():
    with pytest.raises(ValueError):
        quarantine.emit(["x"], "mocha")
