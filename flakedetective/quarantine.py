"""Quarantine output that you can paste, with its limits stated.

pytest can deselect an individual test, so the snippet is exact. Jest cannot
ignore a single test from config, so we emit file-level ignores and say so
instead of pretending otherwise.
"""

from __future__ import annotations

from typing import Sequence, Tuple


def pytest_snippet(test_ids: Sequence[str], ratio: float = 0.0) -> str:
    deselect = "".join('\n    "--deselect={}",'.format(t) for t in test_ids)
    return (
        "# pytest.ini / pyproject.toml [tool.pytest.ini_options]\n"
        "# Quarantined {n} test(s){note}. Remove each line as it is fixed.\n"
        "[tool.pytest.ini_options]\n"
        "addopts = [{deselect}\n]"
    ).format(n=len(test_ids), note=(", flakiness >= {:.0%}".format(ratio) if ratio else ""), deselect=deselect)


def jest_snippet(test_ids: Sequence[str]) -> str:
    files = sorted({t.split("::")[0] for t in test_ids})
    tests = [t.split("::", 1)[1] for t in test_ids if "::" in t]
    lines = [
        "// jest.config.js",
        "// Jest has no per-test config, so scope the ignore to files and skip the",
        "// named tests in place. Both lists come from flakedetective.",
        "module.exports = {",
        "  testPathIgnorePatterns: [{}],".format(", ".join('"<rootDir>/{}"'.format(f) for f in files)),
        "};",
        "",
        "// and in each affected file:",
    ] + ["//   test.skip({!r}, ...);".format(t) for t in tests]
    return "\n".join(lines)


def emit(test_ids: Sequence[str], fmt: str = "pytest", ratio: float = 0.0) -> str:
    if fmt == "pytest":
        return pytest_snippet(test_ids, ratio=ratio)
    if fmt == "jest":
        return jest_snippet(test_ids)
    raise ValueError("unknown format {!r}; choose pytest or jest".format(fmt))
