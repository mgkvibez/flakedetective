# Use flakedetective as a GitHub Action

Your CI already writes JUnit XML. This reads it, keeps a history of runs, and tells you
which tests are flaky instead of which ones failed once.

The one thing that matters: **cache the state directory**. A single run cannot show a
flake, because a flake is a test that both passed and failed. The history is the product.

## Minimal workflow

```yaml
name: flake check
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements-dev.txt
      - run: pytest --junitxml=reports/junit.xml

      # keep the ledger between runs; this is what turns one run into evidence
      - uses: actions/cache@v4
        with:
          path: .flakedetective
          key: flakedetective-${{ github.ref_name }}
          restore-keys: flakedetective-

      - uses: mgkvibez/flakedetective@v0.2.0
        with:
          junit: reports/junit.xml
          state-dir: .flakedetective
          threshold: "0.3"
          fail-on-flaky: "false"
```

The job summary gets a table of tests above the threshold with their flake score, failed
runs over total runs, the likely cause read from the failure text, and a paste-ready
quarantine snippet. `fail-on-flaky: "true"` turns it into a gate.

## Inputs

| input | default | meaning |
| --- | --- | --- |
| `junit` | required | file, glob, or comma-separated list |
| `state-dir` | `.flakedetective` | ledger location; **cache this** |
| `threshold` | `0.0` | minimum flake score to report (0 to 1) |
| `fail-on-flaky` | `false` | fail the step when anything is at or above threshold |
| `top` | `20` | rows in the summary |

## Outputs

| output | meaning |
| --- | --- |
| `flaky-count` | number of tests at or above the threshold |
| `quarantine` | comma-separated test ids |

```yaml
      - uses: mgkvibez/flakedetective@v0.2.0
        id: flakes
        with:
          junit: reports/junit.xml

      - if: steps.flakes.outputs.flaky-count != '0'
        run: echo "quarantine: ${{ steps.flakes.outputs.quarantine }}"
```

## Sharded or matrix suites

Run the Action once per job with that job's file, and give every job the **same**
`state-dir` cache key. Each job contributes its own run record. If instead you merge the
XML first, pass every file to one call: several files in one call are treated as one run,
which is what you want when they are all from the same commit.

## Limits worth knowing

- The ledger is JSONL on disk. It is not a database, and it does not deduplicate across
  branches; use one cache key per branch, as above.
- A flake score needs history. The first run tells you nothing, and the second run can
  only say "this changed", not "this flakes 30% of the time".
- Cause labels are hypotheses read from failure text, not diagnoses. The tool says so in
  its own output; keep saying it.
