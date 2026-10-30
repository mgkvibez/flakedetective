"""A fake suite with three behaviours, so the tool can be tested without luck.

test_total      passes on odd attempts, fails on even ones (flaky, network text)
test_login      always fails (broken, not flaky)
test_serialize  always passes

The attempt counter lives in a file next to this script, so runs are reproducible.
"""

import pathlib
import sys

counter = pathlib.Path(__file__).with_name(".counter")
attempt = int(counter.read_text()) if counter.exists() else 0
counter.write_text(str(attempt + 1))

lines = []
exit_code = 0
if attempt % 2 == 1:
    lines.append("FAILED tests/test_cart.py::test_total - ConnectionError: ECONNREFUSED 127.0.0.1:5432")
    lines.append("E   ConnectionError: ECONNREFUSED 127.0.0.1:5432")
    exit_code = 1
lines.append("FAILED tests/test_auth.py::test_login - AssertionError: assert 401 == 200")
lines.append("E   AssertionError: assert 401 == 200")
exit_code = 1

print("\n".join(lines))
print("2 failed, 1 passed in 0.12s" if exit_code else "1 failed, 2 passed in 0.12s")
sys.exit(exit_code)
