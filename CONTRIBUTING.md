# Contributing

A flaky test is a fact, a cause is a hypothesis. Keep that distinction in the code and the wording.

## Adding a harness

1. Write `parse_<harness>(output, run_index) -> List[Failure]` in `flakedetective/parsers.py`.
2. Register it in `PARSERS` and teach `detect()` its voice.
3. Add a fixture of real output under `tests/fixtures/`.
4. Add a test that fails without your parser and passes with it.

## Rules

- Zero runtime dependencies. Standard library only.
- Never invent a cause: a hypothesis must cite the failure text it came from.
- Exit codes are a contract: 0 clean, 3 flaky, 2 usage.
- Keep the gate green: `bash scripts/verify.sh`.

## What gets rejected

- Anything that runs your suite differently than you do (no hidden plugins, no flags injected).
- Parsers that guess an id that never appeared in the output.
- Reports that call a test "flaky" when it failed every run.
