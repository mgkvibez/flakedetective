"""One test failure observed in one run."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Failure:
    """A single failed test inside a single run."""

    test_id: str
    message: str = ""
    run_index: int = 0
    duration_ms: float = 0.0
    kind: str = "failure"          # "failure" | "error" (collection/teardown)

    @property
    def short_message(self) -> str:
        first = (self.message or "").strip().splitlines()
        return (first[0] if first else "")[:160]


@dataclass
class RunResult:
    """Everything we learned from one execution of the suite."""

    run_index: int
    exit_code: int
    duration_ms: float
    failures: List[Failure] = field(default_factory=list)
    output_path: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.failures
