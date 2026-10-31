# Changelog

## v0.2.0 - 2026-10-31

- **GitHub Action.** `action.yml` plus a testable entry point read the JUnit XML your CI
  already produces, append it to the ledger, and write a ranked job summary with a
  quarantine snippet. `uses: mgkvibez/flakedetective@v0.2.0`. Cache the state directory
  between runs to build history; one run alone can never show a flake.
- **JUnit XML input.** `analyze --junit path/to/*.xml` (repeatable, globs allowed), for
  pytest, jest-junit, go-junit-report, surefire, or anything else that emits JUnit.
  Several files are one run, so a matrix job or sharded suite is not mistaken for several.
- Skipped tests are recorded as neither pass nor failure, because a skip says nothing
  about flakiness. `error` and `failure` are kept distinct so a teardown crash is not
  reported as an assertion.

## v0.1.0 - 2026-10-30

- `run` executes your existing suite command N times and reports which tests are flaky (mixed pass/fail), broken (always failing), or stable.
- Parsers for pytest, jest and unittest with auto-detection; `--parser` to override.
- Cause hypotheses from failure text (network, timeout, shared state, randomness, concurrency, filesystem), each with the count of runs supporting it.
- Per-test repro commands, and quarantine snippets: exact pytest `--deselect`, file-scoped jest ignores with in-place `test.skip` notes.
- Append-only ledger (`.flakedetective/runs.jsonl`) plus `analyze` and `quarantine` subcommands so CI can collect runs and check them later.
- Exit codes: 0 clean, 3 flaky, 2 usage.
- 29 tests, zero dependencies, Python 3.9+.
