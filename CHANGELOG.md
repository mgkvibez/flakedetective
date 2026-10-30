# Changelog

## v0.1.0 - 2026-10-30

- `run` executes your existing suite command N times and reports which tests are flaky (mixed pass/fail), broken (always failing), or stable.
- Parsers for pytest, jest and unittest with auto-detection; `--parser` to override.
- Cause hypotheses from failure text (network, timeout, shared state, randomness, concurrency, filesystem), each with the count of runs supporting it.
- Per-test repro commands, and quarantine snippets: exact pytest `--deselect`, file-scoped jest ignores with in-place `test.skip` notes.
- Append-only ledger (`.flakedetective/runs.jsonl`) plus `analyze` and `quarantine` subcommands so CI can collect runs and check them later.
- Exit codes: 0 clean, 3 flaky, 2 usage.
- 29 tests, zero dependencies, Python 3.9+.
