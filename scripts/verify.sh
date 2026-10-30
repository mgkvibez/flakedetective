#!/usr/bin/env bash
# Release gate for flakedetective: run before every push that claims "done".
# Four independent checks. The smoke asserts the documented exit code (3, the
# "flaky tests found" signal) rather than demanding zero.
set -uo pipefail
cd "$(dirname "$0")/.."

fail() { echo "GATE FAILED: $*"; exit 1; }

echo "== check 1/4: editable install"
python3 -m pip install -q -e ".[dev]" || fail "install"

echo "== check 2/4: version consistency (pyproject vs module)"
pv=$(python3 - <<'PY'
import pathlib, re
try:
    import tomllib
    print(tomllib.loads(pathlib.Path("pyproject.toml").read_text())["project"]["version"])
except ModuleNotFoundError:                     # Python 3.9/3.10 have no tomllib
    text = pathlib.Path("pyproject.toml").read_text()
    print(re.search(r'(?m)^version\s*=\s*"([^"]+)"', text).group(1))
PY
)
mv=$(python3 -c "import flakedetective;print(flakedetective.__version__)")
[ "$pv" = "$mv" ] || { echo "pyproject says $pv, module says $mv"; fail "version drift"; }
echo "version $pv consistent"

echo "== check 3/4: test suite"
python3 -m pytest -q || fail "tests"

echo "== check 4/4: CLI smoke on a deterministic flaky suite (expects exit 3)"
workdir=$(mktemp -d)
cp tests/fixtures/flaky_suite.py "$workdir/suite.py"
( cd "$workdir" && python3 -m flakedetective.cli run --runs 4 --no-color -- python3 suite.py ) > "$workdir/out.txt" 2>&1
code=$?
[ "$code" = "3" ] || { echo "expected exit 3, got $code"; cat "$workdir/out.txt"; fail "cli exit code"; }
grep -q "test_total" "$workdir/out.txt" || { cat "$workdir/out.txt"; fail "cli output"; }
grep -q -- "--deselect=" "$workdir/out.txt" || { cat "$workdir/out.txt"; fail "quarantine snippet missing"; }
echo "smoke ok (exit 3 as documented, flaky test named, quarantine emitted)"
rm -r "$workdir"
echo "ALL CHECKS PASSED"
