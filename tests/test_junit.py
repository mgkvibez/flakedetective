"""JUnit XML ingestion: the shapes real CI tools emit, and the edge cases."""

from __future__ import annotations

import pytest

from flakedetective.junit import JunitError, parse_junit_file, parse_junit_paths

SINGLE = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="suite" tests="4" failures="1" errors="1" skipped="1" time="2.5">
  <testcase classname="tests.test_api" name="test_ok" time="0.5"/>
  <testcase classname="tests.test_api" name="test_bad" time="1.0">
    <failure message="assert 1 == 2">traceback here</failure>
  </testcase>
  <testcase classname="tests.test_api" name="test_boom" time="1.0">
    <error message="RuntimeError: kaboom">traceback</error>
  </testcase>
  <testcase classname="tests.test_api" name="test_skip" time="0.0">
    <skipped message="needs redis"/>
  </testcase>
</testsuite>
"""

WRAPPED = """<?xml version="1.0"?>
<testsuites>
  <testsuite name="a">
    <testcase classname="m" name="test_one" time="0.25"/>
  </testsuite>
  <testsuite name="b">
    <testcase classname="m" name="test_two" time="0.25"/>
  </testsuite>
</testsuites>
"""


def write(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_passes_and_failures_are_separated(tmp_path):
    result = parse_junit_file(write(tmp_path, "one.xml", SINGLE))
    assert result.passes == ["tests.test_api::test_ok"]
    assert [f.test_id for f in result.failures] == [
        "tests.test_api::test_bad",
        "tests.test_api::test_boom",
    ]
    assert [f.kind for f in result.failures] == ["failure", "error"]
    assert result.exit_code == 1
    assert result.complete is True


def test_skipped_is_neither_pass_nor_failure(tmp_path):
    result = parse_junit_file(write(tmp_path, "one.xml", SINGLE))
    everything = result.passes + [f.test_id for f in result.failures]
    assert "tests.test_api::test_skip" not in everything


def test_message_falls_back_to_element_text(tmp_path):
    body = """<testsuite><testcase classname="m" name="t">
      <failure>plain text reason</failure></testcase></testsuite>"""
    result = parse_junit_file(write(tmp_path, "t.xml", body))
    assert result.failures[0].message == "plain text reason"


def test_duration_is_converted_to_milliseconds(tmp_path):
    result = parse_junit_file(write(tmp_path, "one.xml", SINGLE))
    assert result.duration_ms == pytest.approx(2500.0)
    assert result.failures[0].duration_ms == pytest.approx(1000.0)


def test_testsuites_wrapper_is_read(tmp_path):
    result = parse_junit_file(write(tmp_path, "w.xml", WRAPPED))
    assert sorted(result.passes) == ["m::test_one", "m::test_two"]
    assert result.exit_code == 0


def test_missing_classname_falls_back_to_the_name(tmp_path):
    body = '<testsuite><testcase name="lonely" time="0.1"/></testsuite>'
    result = parse_junit_file(write(tmp_path, "n.xml", body))
    assert result.passes == ["lonely"]


def test_a_repeated_test_id_counts_once(tmp_path):
    body = """<testsuite>
      <testcase classname="m" name="dup" time="0.1"/>
      <testcase classname="m" name="dup" time="0.1"/>
    </testsuite>"""
    result = parse_junit_file(write(tmp_path, "d.xml", body))
    assert result.passes == ["m::dup"]


def test_a_file_with_no_testcases_is_incomplete(tmp_path):
    result = parse_junit_file(write(tmp_path, "empty.xml", "<testsuite/>"))
    assert result.complete is False
    assert result.passes == [] and result.failures == []


def test_broken_xml_raises_a_typed_error(tmp_path):
    with pytest.raises(JunitError):
        parse_junit_file(write(tmp_path, "bad.xml", "<testsuite><testcase>"))


def test_a_missing_file_raises_a_typed_error(tmp_path):
    with pytest.raises(JunitError):
        parse_junit_file(str(tmp_path / "nope.xml"))


def test_several_files_become_one_run(tmp_path):
    first = write(tmp_path, "a.xml", WRAPPED)
    second = write(tmp_path, "b.xml", SINGLE)
    merged = parse_junit_paths([first, second], run_index=7)
    assert merged.run_index == 7
    assert merged.exit_code == 1
    assert "m::test_one" in merged.passes
    assert "tests.test_api::test_ok" in merged.passes
    assert len(merged.failures) == 2
    assert merged.output_path.count(",") == 1


def test_union_does_not_double_count_a_shared_test(tmp_path):
    first = write(tmp_path, "a.xml", WRAPPED)
    second = write(tmp_path, "b.xml", WRAPPED)
    merged = parse_junit_paths([first, second])
    assert merged.passes == ["m::test_one", "m::test_two"]


def test_empty_path_list_is_an_error():
    with pytest.raises(JunitError):
        parse_junit_paths([])
