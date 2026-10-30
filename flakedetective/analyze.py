"""Cluster failures by test, then say what the evidence points at.

A flaky test is one that both passed and failed: that is a fact. Why it flakes
is a hypothesis read from the failure text, so every cause carries the count of
runs supporting it and is labelled as a hypothesis rather than a diagnosis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List

from .failures import RunResult

SIGNALS = [
    ("network", re.compile(r"connection|econnrefused|etimedout|socket|dns|proxy|\b(429|502|503|504)\b", re.I),
     "depends on something outside the process",
     "run it with the network stubbed, then again without"),
    ("timeout", re.compile(r"tim(e|ed)?[ -]?out|deadline|took too long|exceeded.*(ms|seconds)", re.I),
     "timing sensitive",
     "run it alone, then under load, and compare durations"),
    ("shared-state", re.compile(r"already exists|duplicate|singleton|leaked|left over|previous test|order|polluted", re.I),
     "leaks or depends on state from another test",
     "run it alone, then the full suite with -p no:randomly"),
    ("randomness", re.compile(r"random|seed|uuid|nondeterministic|faker|shuffle", re.I),
     "uses an unseeded source of variation",
     "pin the seed and see whether the failure disappears"),
    ("concurrency", re.compile(r"race|thread|async|await|deadlock|concurrent", re.I),
     "depends on interleaving",
     "run it single-threaded (--runInBand, -p no:xdist)"),
    ("filesystem", re.compile(r"enoent|permission denied|no such file|read.?only", re.I),
     "depends on the filesystem or a temp path",
     "run it twice in a row and check for a leftover artifact"),
]


@dataclass
class Cluster:
    """Every observation of one test across the runs we have."""

    test_id: str
    runs: int = 0
    fails: int = 0
    passes: int = 0
    messages: List[str] = field(default_factory=list)
    failed_run_indexes: List[int] = field(default_factory=list)

    @property
    def score(self) -> float:
        return (self.fails / self.runs) if self.runs else 0.0

    @property
    def status(self) -> str:
        if self.fails == 0:
            return "stable"
        if self.passes == 0:
            return "broken"
        return "flaky"


@dataclass
class Hypothesis:
    cause: str
    suggestion: str
    evidence: int
    example: str


@dataclass
class Analysis:
    clusters: List[Cluster]
    total_runs: int
    parser: str = "auto"

    @property
    def flaky(self) -> List[Cluster]:
        return sorted([c for c in self.clusters if c.status == "flaky"],
                      key=lambda c: (-c.score, c.test_id))

    @property
    def broken(self) -> List[Cluster]:
        return sorted([c for c in self.clusters if c.status == "broken"], key=lambda c: c.test_id)


def analyze(results: List[RunResult], parser: str = "auto") -> Analysis:
    total = len(results)
    clusters: Dict[str, Cluster] = {}
    for run in results:
        for f in run.failures:
            c = clusters.setdefault(f.test_id, Cluster(test_id=f.test_id))
            if run.run_index not in c.failed_run_indexes:
                c.failed_run_indexes.append(run.run_index)
            if f.message:
                c.messages.append(f.message)
    for c in clusters.values():
        c.runs = total
        c.fails = len(c.failed_run_indexes)
        c.passes = total - c.fails
    return Analysis(clusters=sorted(clusters.values(), key=lambda c: c.test_id),
                    total_runs=total, parser=parser)


def hypotheses(cluster: Cluster) -> List[Hypothesis]:
    """Rank causes by how much evidence the failure text gives each one."""
    found: List[Hypothesis] = []
    for name, pattern, suggestion, _how in SIGNALS:
        hits = [m for m in cluster.messages if pattern.search(m)]
        if hits:
            found.append(Hypothesis(cause=name, suggestion=suggestion,
                                    evidence=len(hits), example=hits[0][:120]))
    found.sort(key=lambda h: (-h.evidence, h.cause))
    return found
