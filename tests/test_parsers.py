import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from flakedetective.parsers import parse, detect

PYTEST_OUT = """FAILED tests/test_cart.py::test_total - AssertionError: assert 3 == 4
E   AssertionError: assert 3 == 4
ERROR tests/test_db.py::test_connect
2 failed, 8 passed in 0.12s"""

JEST_OUT = """FAIL tests/cart.test.js
  \u2715 returns total (12 ms)
Tests: 1 failed, 4 passed"""

UNITTEST_OUT = """FAIL: test_total (tests.test_cart.CartTests)
AssertionError: 3 != 4"""


def test_detect_picks_each_harness():
    assert detect(PYTEST_OUT) == "pytest"
    assert detect(JEST_OUT) == "jest"
    assert detect(UNITTEST_OUT) == "unittest"


def test_pytest_failures_and_messages():
    fails = parse(PYTEST_OUT)
    assert [f.test_id for f in fails] == ["tests/test_cart.py::test_total", "tests/test_db.py::test_connect"]
    assert "assert 3 == 4" in fails[0].message
    assert fails[1].kind == "error"


def test_jest_failures_keep_suite_and_duration():
    fails = parse(JEST_OUT)
    assert fails[0].test_id == "tests/cart.test.js::returns total"
    assert fails[0].duration_ms == 12.0


def test_unittest_failures():
    fails = parse(UNITTEST_OUT)
    assert fails[0].test_id == "tests.test_cart.CartTests.test_total"
    assert "3 != 4" in fails[0].message


def test_unknown_parser_is_a_loud_error():
    try:
        parse("x", parser="mocha")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "pytest" in str(exc)


def test_clean_output_has_no_failures():
    assert parse("5 passed in 0.03s") == []
